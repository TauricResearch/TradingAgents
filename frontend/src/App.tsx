import { useEffect, useState } from "react";

/**
 * F1 shell — V2 three-column layout proof.
 *
 * No mock role/event data and no icons land here. Those arrive in G1 once the
 * typed event reducer (F2) and live run controls (F3) exist, so every rendered
 * state is reconstructible from persisted run events rather than fabricated.
 * This component only proves that the build -> serve -> wheel pipe produces a
 * styled shell from the real visual tokens against the real backend.
 */
export function App() {
  const [config, setConfig] = useState<{ checkpoint_available?: boolean } | null>(
    null,
  );
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/config")
      .then(async (resp) => {
        if (!resp.ok) {
          throw new Error(`HTTP ${resp.status}`);
        }
        return resp.json();
      })
      .then((payload) => {
        if (!cancelled) {
          setConfig(payload);
          setError(null);
        }
      })
      .catch((reason: unknown) => {
        if (!cancelled) {
          setError(reason instanceof Error ? reason.message : String(reason));
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
          <div className="eyebrow">New analysis</div>
          <div className="section-title">
            <h2>分析输入</h2>
          </div>
          <p className="placeholder">
            分析输入控件将在 F3 接入（ticker / 日期 / 分析师 / 研究深度 /
            provider / 模型 / 语言 / checkpoint）。
          </p>
          <div className="shell-note">
            F1 仅验证构建-服务-打包管线。第 2 个有效请求已被拒绝、历史可恢复、
            事件持久化等内容由后端保证。
          </div>
        </aside>

        <main className="main">
          <p className="placeholder">
            工作流全景与辩论时间线将在 G1 / G2 接入真实事件流后渲染。
          </p>
          <div className="shell-note">
            {/* Health check proving the SPA reaches the real FastAPI boundary
                without a second data source. Rendered from `config`, not mock. */}
            后端连通：{" "}
            {error ? (
              <span style={{ color: "var(--red)" }}>失败 · {error}</span>
            ) : config ? (
              <span style={{ color: "var(--green)" }}>
                正常 · checkpoint_available=
                {String(!!config.checkpoint_available)}
              </span>
            ) : (
              <span style={{ color: "var(--muted)" }}>正在握手…</span>
            )}
          </div>
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