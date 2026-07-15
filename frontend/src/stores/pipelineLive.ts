/** Visited stages of the CURRENT in-flight pipeline run (SSE `stage`
 * events), in arrival order. Distinct from `pipelineProgress` (latest
 * stage only): the 3D board needs the full visited set so live mode can
 * show real progression — completed-this-run vs queued — instead of
 * borrowing the previously selected run's node history. Cleared by the
 * terminal `run` event. Not persisted. */
import { create } from "zustand";

interface PipelineLiveState {
  stages: string[];
  push: (stage: string) => void;
  clear: () => void;
}

export const usePipelineLiveStore = create<PipelineLiveState>()((set) => ({
  stages: [],
  push: (stage) =>
    set((state) =>
      state.stages[state.stages.length - 1] === stage
        ? state
        : { stages: [...state.stages, stage] },
    ),
  clear: () => set({ stages: [] }),
}));

export function useLiveStages(): string[] {
  return usePipelineLiveStore((s) => s.stages);
}
