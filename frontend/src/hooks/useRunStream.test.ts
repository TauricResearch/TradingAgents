/**
 * Bug 1 回归测试：onClose 重连不应清空已重放的 turns。
 *
 * useRunStream 的 onClose 重连分支曾调用 dispatch({type:"snapshot"})，
 * 而 reducer 的 snapshot action 返回 createInitialState(snapshot) —— 只有
 * meta+roles 的骨架，导致查看历史 run 时 timeline 在 ~800ms 后突然消失。
 *
 * 修复：onClose 重连时不再 dispatch(snapshot)；state 已有重放数据，
 * 只需读 snapshot 判断是否 terminal，terminal 则 setStatus("closed")，
 * 否则 streamFrom(lastSeqRef) 续订。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import type { PersistedEventDTO, RunSnapshotDTO } from "../api/contracts";

interface CapturedHandlers {
  onEvent: (e: PersistedEventDTO) => void;
  onClose: () => void;
  onError: (e: Error) => void;
}

// vi.mock factories are hoisted above imports, so shared state must live
// inside vi.hoisted to be referenceable from the factory closures.
const mocks = vi.hoisted(() => {
  const getRunMock = vi.fn();
  const closeMock = vi.fn();
  const state: { handlers: CapturedHandlers | null } = { handlers: null };
  return {
    getRunMock,
    closeMock,
    getHandlers: (): CapturedHandlers | null => state.handlers,
    setHandlers: (h: CapturedHandlers | null): void => {
      state.handlers = h;
    },
    resetHandlers: (): void => {
      state.handlers = null;
    },
  };
});

vi.mock("../api/client", () => ({ getRun: mocks.getRunMock }));

vi.mock("../api/eventSource", () => ({
  openRunStream: vi.fn(
    (_runId: string, _after: number, handlers: CapturedHandlers) => {
      mocks.setHandlers(handlers);
      return { close: mocks.closeMock };
    },
  ),
}));

import { useRunStream } from "./useRunStream";

function snap(
  run_id: string,
  status: string,
  latest_sequence: number,
): RunSnapshotDTO {
  return {
    run_id,
    status: status as RunSnapshotDTO["status"],
    ticker: "600519.SS",
    asset_type: "stock",
    analysis_date: "2026-07-21",
    selected_analysts: ["market"],
    max_debate_rounds: 1,
    max_risk_discuss_rounds: 1,
    output_language: "Chinese",
    llm_provider: "deepseek",
    quick_think_llm: "deepseek-chat",
    deep_think_llm: "deepseek-reasoner",
    configured_keys: {},
    created_at: "2026-07-21T12:00:00Z",
    updated_at: "2026-07-21T12:00:00Z",
    latest_sequence,
    artifacts: [],
    redaction_manifest: [],
    event_schema_version: 1,
    metadata: {},
  };
}

function ev(
  run_id: string,
  seq: number,
  type: string,
  payload: Record<string, unknown>,
): PersistedEventDTO {
  return {
    event_id: `${run_id}:${seq}`,
    run_id,
    sequence: seq,
    timestamp: `2026-07-21T12:00:${String(seq).padStart(2, "0")}Z`,
    type,
    payload,
    schema_version: 1,
  };
}

function runStarted(run_id: string, seq = 1): PersistedEventDTO {
  return ev(run_id, seq, "run.started", {
    run_status: "running",
    ticker: "600519.SS",
    asset_type: "stock",
    analysis_date: "2026-07-21",
    selected_analysts: ["market"],
    research_depth: 1,
    max_debate_rounds: 1,
    max_risk_discuss_rounds: 1,
    output_language: "Chinese",
    llm_provider: "deepseek",
    quick_think_llm: "deepseek-chat",
    deep_think_llm: "deepseek-reasoner",
    checkpoint_enabled: false,
  });
}

describe("useRunStream Bug 1: onClose reconnect preserves state", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    mocks.getRunMock.mockReset();
    mocks.closeMock.mockReset();
    mocks.resetHandlers();
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("turns present before onClose survive the reconnect", async () => {
    mocks.getRunMock.mockResolvedValue(snap("run_bug1", "running", 0));
    const { result } = renderHook(() => useRunStream("run_bug1"));

    // 让 getRun promise resolve + streamFrom 注册 subscription
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(mocks.getHandlers()).not.toBeNull();;

    // 重放事件，填充 turns
    await act(async () => {
      mocks.getHandlers()!.onEvent(runStarted("run_bug1", 1));
      mocks.getHandlers()!.onEvent(
        ev("run_bug1", 2, "turn.started", {
          role_instance_id: "run_bug1:analyst.market",
          turn_id: "t1",
          graph_task_id: "gt1",
          graph_step: 1,
          turn_index: 1,
          turn_status: "started",
        }),
      );
      mocks.getHandlers()!.onEvent(
        ev("run_bug1", 3, "turn.output_ready", {
          role_instance_id: "run_bug1:analyst.market",
          turn_id: "t1",
          graph_task_id: "gt1",
          graph_step: 1,
          turn_index: 1,
          turn_status: "output_ready",
          artifact_id: "data:abc123",
        }),
      );
    });

    expect(Object.keys(result.current.state!.turns).length).toBe(1);

    // 模拟 stream 关闭。第二次 getRun 返回 completed（terminal）。
    mocks.getRunMock.mockResolvedValue(snap("run_bug1", "completed", 3));
    await act(async () => {
      mocks.getHandlers()!.onClose();
    });

    // 推进超过 RECONNECT_DELAY_MS（800ms）
    await act(async () => {
      await vi.advanceTimersByTimeAsync(900);
    });

    // Bug 1: onClose 重连曾 dispatch(snapshot) 清空 turns -> length 0
    // 修复后: turns 保留 -> length 1
    expect(Object.keys(result.current.state!.turns).length).toBe(1);
  });

  it("terminal run does not reconnect after onClose (no reconnect storm)", async () => {
    // Bug 2 准确度部分：terminal run 查看历史时，onClose 后应 setStatus("closed")
    // 而不是循环重连 20 次（16s 无反应窗口）。
    mocks.getRunMock.mockResolvedValue(snap("run_term", "completed", 3));
    const { result } = renderHook(() => useRunStream("run_term"));

    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });

    // 重放 3 个事件，最后一个为 terminal
    await act(async () => {
      mocks.getHandlers()!.onEvent(runStarted("run_term", 1));
      mocks.getHandlers()!.onEvent(
        ev("run_term", 2, "turn.started", {
          role_instance_id: "run_term:analyst.market",
          turn_id: "t1",
          graph_task_id: "gt1",
          graph_step: 1,
          turn_index: 1,
          turn_status: "started",
        }),
      );
      mocks.getHandlers()!.onEvent(
        ev("run_term", 3, "run.completed", {
          run_status: "completed",
          summary: "done",
        }),
      );
    });

    // terminal 事件到达后 eventSource 触发 onClose
    await act(async () => {
      mocks.getHandlers()!.onClose();
    });

    // 推进超过 RECONNECT_DELAY_MS
    await act(async () => {
      await vi.advanceTimersByTimeAsync(900);
    });

    // terminal 且所有事件已收到 -> closed，不重连
    expect(result.current.status).toBe("closed");
  });
});
