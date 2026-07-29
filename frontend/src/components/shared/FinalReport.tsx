import type { ReducerState } from "../../state/model";
import { finalReportResolution } from "../../state/selectors";
import { useArtifact } from "../../hooks/useArtifact";
import { SafeMarkdown } from "./SafeMarkdown";

export interface FinalReportProps {
  state: ReducerState;
  run_id: string | null;
}

export function FinalReport({ state, run_id }: FinalReportProps): JSX.Element {
  const resolution = finalReportResolution(state);
  const artifact_id = resolution.status === "ready" ? resolution.artifact_id : null;
  const { content, loading, error, reload } = useArtifact(run_id, artifact_id);

  if (resolution.status === "ambiguous") {
    return (
      <section className="final-report integrity-error" aria-live="polite">
        <span className="eyebrow">完整报告</span>
        <h2>完整报告存在完整性冲突</h2>
        <p>发现多个完整报告候选，系统不会自行猜测。请在高级审计中核对运行文件。</p>
      </section>
    );
  }
  if (resolution.status === "missing") {
    return (
      <section className="final-report" aria-live="polite">
        <span className="eyebrow">完整报告</span>
        <h2>完整报告暂不可用</h2>
        <p>该运行仍可阅读已保存的阶段报告；旧运行只有存在唯一完整报告文件时才会自动回退。</p>
      </section>
    );
  }
  if (loading) {
    return (
      <section className="final-report">
        <span className="eyebrow">完整报告</span>
        <div className="placeholder">正在加载完整研究结论…</div>
      </section>
    );
  }
  if (error !== null || content === null) {
    return (
      <section className="final-report integrity-error" aria-live="polite">
        <span className="eyebrow">完整报告</span>
        <h2>完整报告读取失败</h2>
        <p>{error ?? "报告内容为空。"}</p>
        <button type="button" className="filter active" onClick={reload}>
          重试读取
        </button>
      </section>
    );
  }

  return (
    <section className="final-report">
      <div className="final-report-head">
        <div>
          <span className="eyebrow">最终完整结论</span>
          <h2>{state.meta.ticker} 研究报告</h2>
        </div>
        {state.meta.final_signal && (
          <span className="final-signal">{state.meta.final_signal}</span>
        )}
      </div>
      {(state.meta.degraded_data_sources?.length ?? 0) > 0 && (
        <div className="degradation-banner">
          本次分析使用了降级数据源；完整影响范围见报告末尾的数据可用性说明。
        </div>
      )}
      {resolution.source === "legacy_locator" && (
        <div className="legacy-note">这是基于旧运行的唯一完整报告文件回退结果。</div>
      )}
      <SafeMarkdown content={content} />
    </section>
  );
}
