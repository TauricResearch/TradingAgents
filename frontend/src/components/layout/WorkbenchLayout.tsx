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
import { ResearchDocument } from "../timeline/ResearchDocument";
import { Inspector } from "../inspector/Inspector";
import type { InspectorTab } from "../inspector/Inspector";
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { useRunHistory } from "../../hooks/useRunHistory";
import { currentRunStatus } from "../../state/selectors";

function preferredAuditTurn(state: NonNullable<ReturnType<typeof useWorkbenchStore>["stream"]["state"]>): string | null {
  const turns = Object.values(state.turns).sort(
    (left, right) => right.turn_index - left.turn_index,
  );
  const active = turns.find((turn) =>
    turn.status === "started" || turn.status === "output_ready" || turn.status === "resumed",
  );
  return active?.turn_id ?? turns[0]?.turn_id ?? null;
}

export function WorkbenchLayout(): JSX.Element {
  const { stream, run_id } = useWorkbenchStore();
  const state = stream.state;
  const history = useRunHistory();
  const [selectedTurn, setSelectedTurn] = useState<string | null>(null);
  const [inspectorTab, setInspectorTab] = useState<InspectorTab>("role-input");
  const [selectionRunId, setSelectionRunId] = useState<string | null>(null);
  const [userHasSelected, setUserHasSelected] = useState(false);

  // A selection belongs to a run, not the whole browser session.  New/history
  // runs receive the latest meaningful stage; once the user clicks a stage we
  // preserve that choice while SSE events continue to arrive.
  useEffect(() => {
    if (state === null || state.meta.run_id === "") return;
    if (selectionRunId !== state.meta.run_id) {
      setSelectionRunId(state.meta.run_id);
      setUserHasSelected(false);
      setSelectedTurn(preferredAuditTurn(state));
      setInspectorTab("role-input");
      return;
    }
    if (!userHasSelected) {
      setSelectedTurn(preferredAuditTurn(state));
    }
  }, [state, selectionRunId, userHasSelected]);

  const handleTurnSelected = (turn_id: string): void => {
    setSelectedTurn(turn_id);
    setSelectionRunId(state?.meta.run_id ?? null);
    setUserHasSelected(true);
    setInspectorTab("role-input");
  };

  // G3: clicking a role card in the workflow map selects that role's latest
  // turn and surfaces it in the Inspector's role-input tab.
  const handleRoleSelected = (actor_id: string): void => {
    const turn_id = state?.roles[actor_id]?.latest_turn_id;
    if (turn_id) {
      handleTurnSelected(turn_id);
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
              <ResearchDocument
                state={state}
                run_id={run_id}
                onTurnSelected={handleTurnSelected}
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
