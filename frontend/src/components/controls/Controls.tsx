/**
 * F3 - Left sidebar controls for the TradingAgents workbench.
 *
 * Pure renderer of useConfig() selection state + useWorkbenchStore() run state.
 * Owns no selection state itself; every input dispatches back into the hook.
 * Visual classes reference the V2 workbench stylesheet (.eyebrow, .section-title,
 * .input-group, .grid-2, .analysts, .check, .key-status, .ok, .primary,
 * .primary.running) where they exist.
 */
import { useState } from "react";
import { useConfig } from "../../hooks/useConfig";
import { useWorkbenchStore } from "../../state/WorkbenchStore";
import { createRun, cancelRun } from "../../api/client";
import type { ResearchDepth } from "../../api/contracts";

const DEPTH_OPTIONS: ResearchDepth[] = [1, 3, 5];

export interface ControlsProps {
  /** Called after a new run is successfully created so the history list refreshes. */
  refreshHistory?: () => Promise<void>;
}

export function Controls({ refreshHistory }: ControlsProps = {}): JSX.Element {
  const cfg = useConfig();
  const store = useWorkbenchStore();
  const [apiError, setApiError] = useState<string | null>(null);
  const [starting, setStarting] = useState<boolean>(false);

  const runActive =
    store.stream.status === "live" ||
    store.stream.status === "replaying" ||
    store.stream.status === "loading";

  function handleStart(): void {
    const req = cfg.buildRequest();
    if (req === null) return;
    setApiError(null);
    setStarting(true);
    createRun(req)
      .then((snap) => {
        store.selectRun(snap.run_id);
        refreshHistory?.();
      })
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        setStarting(false);
      });
  }

  function handleCancel(): void {
    if (store.run_id === null) return;
    cancelRun(store.run_id)
      .then(() => refreshHistory?.())
      .catch((e: unknown) => {
        setApiError(e instanceof Error ? e.message : String(e));
      });
  }

  const startDisabled =
    cfg.validationError !== null || runActive || starting || cfg.loading;

  return (
    <div className="controls">
      <div className="eyebrow">New analysis</div>
      <div className="section-title">
        <h2>分析输入</h2>
      </div>

      <div className="input-group">
        <label htmlFor="ctrl-ticker">股票代码</label>
        <input
          id="ctrl-ticker"
          type="text"
          value={cfg.ticker}
          onChange={(e) => cfg.setTicker(e.target.value)}
          placeholder="如 600519 / AAPL"
        />
      </div>

      <div className="input-group">
        <label htmlFor="ctrl-date">分析日期</label>
        <input
          id="ctrl-date"
          type="date"
          value={cfg.analysis_date}
          onChange={(e) => cfg.setAnalysisDate(e.target.value)}
        />
      </div>

      <div className="input-group">
        <label htmlFor="ctrl-depth">研究深度</label>
        <select
          id="ctrl-depth"
          value={String(cfg.research_depth)}
          onChange={(e) => {
            const v = Number(e.target.value);
            if (v === 1 || v === 3 || v === 5) cfg.setResearchDepth(v);
          }}
        >
          {DEPTH_OPTIONS.map((d) => (
            <option key={d} value={String(d)}>
              {d} 轮
            </option>
          ))}
        </select>
      </div>

      <div className="input-group">
        <label htmlFor="ctrl-preset">研究预设</label>
        <select
          id="ctrl-preset"
          value={cfg.selected_preset ?? "custom"}
          onChange={(e) => cfg.setAnalystPreset(e.target.value)}
          disabled={cfg.loading}
        >
          {cfg.selected_preset === null && <option value="custom">自定义组合</option>}
          {cfg.config?.presets.map((preset) => (
            <option key={preset.id} value={preset.id}>
              {preset.label}
            </option>
          ))}
        </select>
        <small>预设只调整分析师启停与顺序，后续研究和风控链路始终执行。</small>
      </div>

      <div className="input-group">
        <label>分析师</label>
        <div className="analysts grid-2">
          {cfg.config?.analysts.map((a) => (
            <label
              key={a.id}
              className="check"
              htmlFor={`ctrl-analyst-${a.id}`}
            >
              <input
                id={`ctrl-analyst-${a.id}`}
                type="checkbox"
                checked={cfg.selected_analysts.includes(a.id)}
                onChange={() => cfg.toggleAnalyst(a.id)}
              />
              {a.id}
            </label>
          ))}
        </div>
      </div>

      <div className="input-group">
        <label htmlFor="ctrl-provider">LLM Provider</label>
        <select
          id="ctrl-provider"
          value={cfg.llm_provider}
          onChange={(e) => cfg.setLlmProvider(e.target.value)}
          disabled={cfg.loading}
        >
          {cfg.config?.providers.map((p) => (
            <option key={p.id} value={p.id}>
              {p.id}
              {p.configured ? " · 已配置" : " · 未配置"}
            </option>
          ))}
        </select>
        {cfg.selectedProvider !== null && (
          <div className="key-status">
            {cfg.selectedProvider.requires_api_key === false ? (
              <span className="ok">无需 API Key</span>
            ) : cfg.configured_keys[cfg.llm_provider] === true ? (
              <span className="ok">已配置</span>
            ) : (
              <span style={{ color: "var(--red)" }}>未配置</span>
            )}
          </div>
        )}
      </div>

      <div className="input-group">
        <label htmlFor="ctrl-quick">快速思考模型</label>
        <select
          id="ctrl-quick"
          value={cfg.quick_think_llm}
          onChange={(e) => cfg.setQuickThinkLlm(e.target.value)}
          disabled={cfg.loading || cfg.quickOptions.length === 0}
        >
          {cfg.quickOptions.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      <div className="input-group">
        <label htmlFor="ctrl-deep">深度思考模型</label>
        <select
          id="ctrl-deep"
          value={cfg.deep_think_llm}
          onChange={(e) => cfg.setDeepThinkLlm(e.target.value)}
          disabled={cfg.loading || cfg.deepOptions.length === 0}
        >
          {cfg.deepOptions.map((m) => (
            <option key={m.id} value={m.id}>
              {m.label}
            </option>
          ))}
        </select>
      </div>

      <div className="input-group">
        <label htmlFor="ctrl-lang">输出语言</label>
        <select
          id="ctrl-lang"
          value={cfg.output_language}
          onChange={(e) => cfg.setOutputLanguage(e.target.value)}
          disabled={cfg.loading}
        >
          {cfg.config?.output_languages.map((lang) => (
            <option key={lang} value={lang}>
              {lang}
            </option>
          ))}
        </select>
      </div>

      <div className="input-group">
        <label className="check" htmlFor="ctrl-checkpoint">
          <input
            id="ctrl-checkpoint"
            type="checkbox"
            checked={cfg.checkpoint_enabled}
            onChange={(e) => cfg.setCheckpointEnabled(e.target.checked)}
            disabled={!cfg.config?.checkpoint_available}
          />
          启用 Checkpoint 续跑
        </label>
      </div>

      <div className="input-group">
        <label className="check" htmlFor="ctrl-portfolio-enabled">
          <input
            id="ctrl-portfolio-enabled"
            type="checkbox"
            checked={cfg.portfolio_enabled}
            onChange={(e) => cfg.setPortfolioEnabled(e.target.checked)}
          />
          启用当前标的的组合约束
        </label>
        <small>
          可选：据现金、持仓和上限给出可执行数量；不会保存模型私有推理。
        </small>
      </div>

      {cfg.portfolio_enabled && (
        <>
          <div className="input-group">
            <label htmlFor="ctrl-portfolio-cash">可用现金（CNY）</label>
            <input
              id="ctrl-portfolio-cash"
              type="number"
              min="0"
              step="any"
              value={cfg.portfolio_cash}
              onChange={(e) => cfg.setPortfolioCash(e.target.value)}
              placeholder="如 100000"
            />
          </div>
          <div className="input-group">
            <label htmlFor="ctrl-portfolio-price">参考价格</label>
            <input
              id="ctrl-portfolio-price"
              type="number"
              min="0"
              step="any"
              value={cfg.portfolio_mark_price}
              onChange={(e) => cfg.setPortfolioMarkPrice(e.target.value)}
              placeholder="如 1500"
            />
          </div>
          <div className="input-group grid-2">
            <label htmlFor="ctrl-portfolio-quantity">
              持仓数量
              <input
                id="ctrl-portfolio-quantity"
                type="number"
                min="0"
                step="1"
                value={cfg.portfolio_quantity}
                onChange={(e) => cfg.setPortfolioQuantity(e.target.value)}
              />
            </label>
            <label htmlFor="ctrl-portfolio-sellable">
              可卖数量
              <input
                id="ctrl-portfolio-sellable"
                type="number"
                min="0"
                step="1"
                value={cfg.portfolio_sellable_quantity}
                onChange={(e) => cfg.setPortfolioSellableQuantity(e.target.value)}
                placeholder="默认等于持仓"
              />
            </label>
          </div>
          <div className="input-group grid-2">
            <label htmlFor="ctrl-portfolio-cost">
              持仓成本
              <input
                id="ctrl-portfolio-cost"
                type="number"
                min="0"
                step="any"
                value={cfg.portfolio_average_cost}
                onChange={(e) => cfg.setPortfolioAverageCost(e.target.value)}
                placeholder="默认等于参考价"
              />
            </label>
            <label htmlFor="ctrl-portfolio-max-weight">
              单标的上限（0-1）
              <input
                id="ctrl-portfolio-max-weight"
                type="number"
                min="0.01"
                max="1"
                step="0.01"
                value={cfg.portfolio_max_weight}
                onChange={(e) => cfg.setPortfolioMaxWeight(e.target.value)}
              />
            </label>
          </div>
        </>
      )}

      {cfg.validationError !== null && (
        <div className="error-text" style={{ color: "var(--red)" }}>
          {cfg.validationError}
        </div>
      )}
      {apiError !== null && (
        <div className="error-text" style={{ color: "var(--red)" }}>
          {apiError}
        </div>
      )}

      <div className="actions">
        {runActive ? (
          <>
            <button type="button" className="primary running" disabled>
              分析进行中
            </button>
            <button type="button" className="cancel" onClick={handleCancel}>
              取消
            </button>
          </>
        ) : (
          <button
            type="button"
            className="primary"
            onClick={handleStart}
            disabled={startDisabled}
          >
            {starting ? "启动中…" : "开始分析"}
          </button>
        )}
      </div>
    </div>
  );
}
