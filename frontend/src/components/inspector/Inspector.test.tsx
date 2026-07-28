import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ArtifactRecord, ReducerState, RunMeta, Turn } from "../../state/model";
import { Inspector } from "./Inspector";

const mockStore = vi.hoisted(() => ({ useWorkbenchStore: vi.fn() }));
const mockClient = vi.hoisted(() => ({ readArtifactText: vi.fn() }));
vi.mock("../../state/WorkbenchStore", () => ({ useWorkbenchStore: mockStore.useWorkbenchStore }));
vi.mock("../../api/client", () => ({ readArtifactText: mockClient.readArtifactText }));

function meta(): RunMeta {
  return {
    run_id: "switch-run", status: "running", ticker: "AAPL", asset_type: "stock",
    analysis_date: "2026-07-28", selected_analysts: ["market"], research_depth: 3,
    max_debate_rounds: 2, max_risk_discuss_rounds: 2, output_language: "zh",
    llm_provider: "openai", quick_think_llm: "quick", deep_think_llm: "deep",
    configured_keys: {}, checkpoint_enabled: false, created_at: "2026-07-28T00:00:00Z",
    updated_at: "2026-07-28T00:00:00Z", latest_sequence: 1,
    redaction_manifest: [], event_schema_version: 1,
  };
}
function artifact(id: string, turn_id: string, kind: string, captures: string[] = []): ArtifactRecord {
  return { artifact_id: id, kind, media_type: "text/markdown", content_sha256: `sha-${id}`,
    byte_size: 10, locator: `/${id}`, written_sequence: 1, input_capture_kinds: captures, turn_id };
}
function makeTurn(id: string, actor_id: string, model: string, field: string, output: string): { state: ReducerState; turn: Turn } {
  const current: Turn = {
    turn_id: id, role_instance_id: `switch-run:${actor_id}`, actor_id, turn_index: 1,
    status: "completed", duration_ms: 1000, artifact_id: `${id}-output`,
    model_call_ids: [`${id}-model`], tool_call_ids: [], vendor_call_ids: [],
  };
  const artifacts = [
    artifact(`${id}-state`, id, "state_snapshot", ["state_snapshot"]),
    artifact(`${id}-prompt`, id, "prompt_snapshot", ["prompt_snapshot"]),
    artifact(`${id}-output`, id, "response"),
  ];
  const state: ReducerState = {
    meta: meta(), roles: {}, turns: { [id]: current },
    model_calls: { [`${id}-model`]: {
      model_call_id: `${id}-model`, turn_id: id, graph_task_id: "task", attempt_id: "attempt",
      provider: `${id}-provider`, model, invocation_path: "test", status: "completed",
      prompt_artifact_ids: [`${id}-prompt`],
    } },
    tool_calls: {}, vendor_calls: {}, artifacts: Object.fromEntries(artifacts.map((a) => [a.artifact_id, a])),
    reports: [], graph_tasks: {}, latest_graph_step: 1,
  };
  mockClient.readArtifactText.mockImplementation(async (_run: string, artifactId: string) => {
    if (artifactId === `${id}-state`) return JSON.stringify({ state_fields: { [`${id}_field`]: field } });
    if (artifactId === `${id}-prompt`) return `${id} prompt`;
    if (artifactId === `${id}-output`) return output;
    return "{}";
  });
  return { state, turn: current };
}
function setStore(state: ReducerState): void {
  mockStore.useWorkbenchStore.mockReturnValue({ run_id: "switch-run", selectRun: vi.fn(), stream: { state, status: "live", error: null, close: vi.fn() } });
}

describe("Inspector", () => {
  beforeEach(() => vi.clearAllMocks());

  it("remounts all turn-scoped content when selection changes", async () => {
    const a = makeTurn("turn-a", "researcher.bull", "model-a", "A evidence", "A output");
    setStore(a.state);
    const { rerender } = render(<Inspector selectedTurnId="turn-a" />);
    expect(screen.getByText("turn-a-provider")).toBeInTheDocument();
    expect(screen.getByText("model-a")).toBeInTheDocument();
    expect(await screen.findByText("A evidence")).toBeInTheDocument();
    expect(await screen.findByText("A output")).toBeInTheDocument();

    const b = makeTurn("turn-b", "researcher.bear", "model-b", "B evidence", "B output");
    setStore(b.state);
    rerender(<Inspector selectedTurnId="turn-b" />);
    expect(screen.getByText("turn-b-provider")).toBeInTheDocument();
    expect(screen.getByText("model-b")).toBeInTheDocument();
    expect(await screen.findByText("B evidence")).toBeInTheDocument();
    expect(await screen.findByText("B output")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByText("turn-a-provider")).not.toBeInTheDocument();
      expect(screen.queryByText("model-a")).not.toBeInTheDocument();
      expect(screen.queryByText("A evidence")).not.toBeInTheDocument();
      expect(screen.queryByText("A output")).not.toBeInTheDocument();
    });
  });
});
