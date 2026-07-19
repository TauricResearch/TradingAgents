/**
 * F3 - Run history sidebar list.
 *
 * Renders the newest-first list of runs from GET /api/runs. Each item shows
 * the ticker (strong) and a colored status badge in .history-top, plus the
 * created_at locale string and final_signal (if present) in .history-sub.
 * Clicking an item calls selectRun(run_id) from the workbench store; the
 * active item (matching store.run_id) gets the .active class.
 *
 * RunSummaryDTO has no research_depth, so depth is not rendered here.
 */
import type { CSSProperties } from "react";
import type { RunStatusLiteral, RunSummaryDTO } from "../../api/contracts";
import { useRunHistory } from "../../hooks/useRunHistory";
import { useWorkbenchStore } from "../../state/WorkbenchStore";

interface StatusBadge {
  /** Extra class for completed (green) -> "ok"; empty for others. */
  className: string;
  /** CSS color token applied via inline style. */
  color: string;
  /** Chinese status label. */
  label: string;
  /** Whether to prefix a pulsing dot (running only). */
  dot: boolean;
}

const STATUS_BADGES: Record<RunStatusLiteral, StatusBadge> = {
  completed: { className: "ok", color: "var(--green)", label: "已完成", dot: false },
  failed: { className: "", color: "var(--red)", label: "失败", dot: false },
  cancelled: { className: "", color: "var(--muted)", label: "已取消", dot: false },
  interrupted: { className: "", color: "var(--gold)", label: "已中断", dot: false },
  running: { className: "", color: "var(--gold)", label: "运行中", dot: true },
  cancel_requested: { className: "", color: "var(--gold)", label: "取消中", dot: false },
  created: { className: "", color: "var(--muted)", label: "已创建", dot: false },
};

export function RunHistory(): JSX.Element {
  const { runs, loading, error } = useRunHistory();
  const { run_id, selectRun } = useWorkbenchStore();

  return (
    <section className="history">
      <div className="section-title">
        <h2>最近运行</h2>
      </div>
      {error ? (
        <p className="placeholder">加载失败：{error.message}</p>
      ) : loading && runs.length === 0 ? (
        <p className="placeholder">加载中…</p>
      ) : runs.length === 0 ? (
        <p className="placeholder">暂无运行记录</p>
      ) : (
        <ul>
          {runs.map((run: RunSummaryDTO) => {
            const badge = STATUS_BADGES[run.status];
            const badgeStyle: CSSProperties = { color: badge.color };
            const isActive = run.run_id === run_id;
            const itemClassName = `history-item${isActive ? " active" : ""}`;
            const badgeClassName = `status-badge${badge.className ? ` ${badge.className}` : ""}`;
            return (
              <li
                key={run.run_id}
                className={itemClassName}
                onClick={() => selectRun(run.run_id)}
              >
                <div className="history-top">
                  <strong>{run.ticker}</strong>
                  <span className={badgeClassName} style={badgeStyle}>
                    {badge.dot ? `● ${badge.label}` : badge.label}
                  </span>
                </div>
                <div className="history-sub">
                  <span>{new Date(run.created_at).toLocaleString()}</span>
                  {run.final_signal ? (
                    <span> · {run.final_signal}</span>
                  ) : null}
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
