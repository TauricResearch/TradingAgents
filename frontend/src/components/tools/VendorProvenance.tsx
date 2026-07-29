/**
 * G3 - Vendor data-call provenance panel for the 数据与工具 inspector tab.
 *
 * Lists all VendorCalls observed for the selected turn, sourced from the live
 * workbench store. Each .source-line entry shows the vendor (bold), method,
 * stage, a colored status dot (completed=green, failed=red, progress=gold,
 * interrupted=muted), and duration_ms when present. Shows .placeholder when
 * the run is not loaded, turn_id is null, or no calls match the turn.
 *
 * Per spec: derive vendor_calls in-component (state.vendor_calls filtered by
 * turn_id); selectors.ts is NOT modified.
 */
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import type { VendorCall } from "../../state/model";

export interface VendorProvenanceProps {
  turn_id: string | null;
}

type VendorStatus = VendorCall["status"];

const VENDOR_STATUS_COLOR: Record<VendorStatus, string> = {
  completed: "var(--green)",
  failed: "var(--red)",
  progress: "var(--amber)",
  interrupted: "var(--muted)",
};

const VENDOR_STATUS_LABEL: Record<VendorStatus, string> = {
  completed: "已完成",
  failed: "失败",
  progress: "进行中",
  interrupted: "已中断",
};

const FAILURE_LABELS: Record<string, string> = {
  network_unreachable: "网络不可达，已尝试备用源",
  not_configured: "未配置访问凭证",
  rate_limited: "请求受限",
  no_market_data: "该源无可用数据",
  vendor_error: "数据源调用失败",
};

export function VendorProvenance({
  turn_id,
}: VendorProvenanceProps): JSX.Element {
  const { stream } = useWorkbenchStore();
  const state = stream.state;

  const calls: VendorCall[] =
    state !== null && turn_id !== null
      ? Object.values(state.vendor_calls).filter(
          (vc) => vc.turn_id === turn_id,
        )
      : [];

  return (
    <section className="vendor-provenance">
      <span className="eyebrow">数据来源</span>
      {calls.length === 0 ? (
        <div className="placeholder">本轮无数据调用</div>
      ) : (
        <ul className="sources">
          {calls.map((vc) => {
            const color = VENDOR_STATUS_COLOR[vc.status];
            const label = VENDOR_STATUS_LABEL[vc.status];
            return (
              <li key={vc.vendor_call_id} className="source-line">
                <span
                  className="status-dot"
                  style={{ backgroundColor: color }}
                  role="img"
                  aria-label={label}
                />
                <span className="vendor">{vc.vendor}</span>
                <span className="method">{vc.method}</span>
                <span className="stage">{vc.stage}</span>
                {vc.status === "failed" && vc.failure_code && (
                  <span className="failure-reason">
                    {FAILURE_LABELS[vc.failure_code] ?? vc.failure_code}
                  </span>
                )}
                {vc.fallback_chain && vc.fallback_chain.length > 1 && (
                  <span className="fallback-chain">
                    备用顺序：{vc.fallback_chain.join(" → ")}
                  </span>
                )}
                {vc.duration_ms !== undefined && (
                  <span className="duration">{vc.duration_ms}ms</span>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
