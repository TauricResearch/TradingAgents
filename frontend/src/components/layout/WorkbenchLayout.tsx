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
import { Controls } from "../controls/Controls";
import { RunHistory } from "../history/RunHistory";
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { currentRunStatus } from "../../state/selectors";

export function WorkbenchLayout(): JSX.Element {
  const { stream } = useWorkbenchStore();
  const state = stream.state;

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
              <p className="placeholder">
                工作流全景与辩论时间线将在 G1 / G2 接入真实事件流后渲染。
              </p>
            </>
          ) : (
            <p className="placeholder">选择一次运行或发起新分析</p>
          )}
        </main>

        <aside className="inspector">
          <div className="eyebrow">Audit inspector</div>
          <div className="section-title">
            <h2>审计检查器</h2>
          </div>
          <p className="placeholder">
            角色输入 / 数据与工具 / 产物 / 本次输入 四个审计视图将在 G3 接入。
          </p>
          <p className="disclaimer">
            股票数据、新闻内容和提示上下文仍会发送给本次选择的数据商与 LLM
            Provider。localhost 仅表示网页不对公网提供服务。
          </p>
        </aside>
      </div>
    </div>
  );
}
