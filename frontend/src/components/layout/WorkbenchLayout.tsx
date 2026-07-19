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
import { useState } from "react";
import { Controls } from "../controls/Controls";
import { RunHistory } from "../history/RunHistory";
import { WorkflowMap } from "../workflow/WorkflowMap";
import { Timeline } from "../timeline/Timeline";
import { Inspector } from "../inspector/Inspector";
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { currentRunStatus } from "../../state/selectors";

export function WorkbenchLayout(): JSX.Element {
  const { stream } = useWorkbenchStore();
  const state = stream.state;
  const [timelineFilter, setTimelineFilter] = useState<string>("");
  const [selectedTurn, setSelectedTurn] = useState<string | null>(null);

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
          <Controls />
          <RunHistory />
        </aside>

        <main className="main">
          {state ? (
            <>
              <div className="eyebrow">Active run</div>
              <div className="section-title">
                <h2>{state.meta.ticker}</h2>
                <span className="placeholder">
                  {currentRunStatus(state)} · #{state.meta.latest_sequence}
                </span>
              </div>
              <WorkflowMap />
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
              <WorkflowMap />
            </>
          )}
        </main>

        <aside className="inspector">
          <Inspector selectedTurnId={selectedTurn} />
        </aside>
      </div>
    </div>
  );
}
