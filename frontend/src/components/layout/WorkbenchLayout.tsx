/**
 * F3 - Three-column workbench shell wiring F2 (run stream) and F3 (controls +
 * run history) together.
 *
 * Assumes it is rendered INSIDE a <WorkbenchProvider>; App.tsx will be updated
 * separately to wrap with the provider and render this layout. Do not modify
 * App.tsx from this module.
 *
 * Layout:
 *   .app
 *     .topbar  (brand + localhost pill + disclaimer)
 *     .layout
 *       .sidebar   (Controls + RunHistory)
 *       .main      (run status strip when a run is selected, else placeholder)
 *       .inspector (audit placeholder, G3)
 */
import { useEffect, useState } from "react";
import { Controls } from "../controls/Controls";
import { RunHistory } from "../history/RunHistory";
import { WorkflowMap } from "../workflow/WorkflowMap";
import { Timeline } from "../timeline/Timeline";
import { Inspector } from "../inspector/Inspector";
import { SwarmStatusCard } from "../status/SwarmStatusCard";
import { MarketChart } from "../market/MarketChart";
import type { InspectorTab } from "../inspector/Inspector";
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { useRunHistory } from "../../hooks/useRunHistory";
import { currentRunStatus } from "../../state/selectors";

const TERMINAL_RUN_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "interrupted",
]);

export function WorkbenchLayout(): JSX.Element {
  const { stream } = useWorkbenchStore();
  const state = stream.state;
  const history = useRunHistory();
  const [timelineFilter, setTimelineFilter] = useState<string>("");
  const [selectedTurn, setSelectedTurn] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("role-input");

  // A run first appears in history as "running" after POST /api/runs. Refresh
  // once its SSE state reaches a terminal status so the sidebar does not keep
  // showing a stale running badge until the page is reloaded.
  useEffect(() => {
    if (state?.meta.run_id && TERMINAL_RUN_STATUSES.has(state.meta.status)) {
      void history.refresh();
    }
  }, [history.refresh, state?.meta.run_id, state?.meta.status]);

  // G3: clicking a role card in the workflow map selects that role's latest
  // turn and surfaces it in the Inspector's role-input tab.
  const handleRoleSelected = (actor_id: string): void => {
    const turn_id = state?.roles[actor_id]?.latest_turn_id;
    if (turn_id) {
      setSelectedTurn(turn_id);
      setInspectorTab("role-input");
    }
  };

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">TA</span>
          TradingAgents{" "}
          <span className="brand-sub">Research Console</span>
        </div>
        <div className="top-meta">
          <span className="local-pill">● localhost</span>
          <span>仅用于研究，不构成投资建议</span>
        </div>
      </header>

      <div className="layout">
        <aside className="sidebar">
          <Controls refreshHistory={history.refresh} />
          <RunHistory
            runs={history.runs}
            loading={history.loading}
            error={history.error}
          />
        </aside>

        <main className="main">
          {state && state.meta.run_id ? (
            <>
              <div className="eyebrow">Active run</div>
              <div className="section-title">
                <h2>{state.meta.ticker}</h2>
                <span className="placeholder">
                  {currentRunStatus(state)} · #{state.meta.latest_sequence}
                </span>
              </div>
              <SwarmStatusCard state={state} streamStatus={stream.status} />
              <MarketChart
                run_id={state.meta.run_id}
                latest_sequence={state.meta.latest_sequence}
                artifact_count={Object.keys(state.artifacts).length}
              />
              <WorkflowMap onRoleSelected={handleRoleSelected} />
              <Timeline
                filter={timelineFilter}
                onTurnSelected={setSelectedTurn}
                onFilterChange={setTimelineFilter}
              />
            </>
          ) : (
            <>
              <div className="eyebrow">Workflow</div>
              <div className="section-title">
                <h2>工作流全景</h2>
              </div>
              <WorkflowMap onRoleSelected={handleRoleSelected} />
            </>
          )}
        </main>

        <aside className="inspector">
          <Inspector
            selectedTurnId={selectedTurn}
            activeTab={inspectorTab}
            onTabChange={setInspectorTab}
          />
        </aside>
      </div>
    </div>
  );
}
