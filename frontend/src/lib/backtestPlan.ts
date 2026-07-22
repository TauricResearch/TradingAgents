/** Client mirror of the backend's run-planning math (backtest_job.py):
 * duration → bars → decisions → time estimate. Display-only — the backend
 * remains the enforcement point (large runs get a 400-with-estimate until
 * confirmed) — but the numbers must agree so the operator sees the same
 * plan before and after clicking Run. */

export const MIN_HISTORY = 60;
export const MAX_LLM_DECISIONS = 300;
export const LARGE_RUN_DECISIONS = 20_000;
/** measured full-pipeline throughput with precomputed indicators */
const EST_DECISIONS_PER_SECOND = 60;

const DURATION_SECONDS: Record<string, number> = {
  "1D": 86_400,
  "7D": 7 * 86_400,
  "30D": 30 * 86_400,
  "1Y": 365 * 86_400,
};

const TIMEFRAME_SECONDS: Record<string, number> = {
  "1m": 60,
  "5m": 300,
  "15m": 900,
  "30m": 1800,
  "1h": 3600,
  "4h": 14_400,
  "1d": 86_400,
  "1w": 604_800,
};

/** assets that do NOT trade 24/7 — daily bar counts scale by trading days */
const MARKET_CLOSURE_SYMBOLS = new Set(["XAUUSD"]);

export interface RunPlan {
  bars: number;
  decisions: number;
  estMinutes: number;
  needsConfirm: boolean;
  llmCapped: boolean;
}

export function planRun(
  symbol: string,
  timeframe: string,
  duration: string,
  useLlm: boolean,
): RunPlan | null {
  const seconds = DURATION_SECONDS[duration];
  const tfSeconds = TIMEFRAME_SECONDS[timeframe];
  if (!seconds || !tfSeconds) return null;
  let span = Math.max(1, Math.ceil(seconds / tfSeconds));
  if (MARKET_CLOSURE_SYMBOLS.has(symbol) && timeframe === "1d") {
    span = Math.max(1, Math.ceil((span * 5) / 7));
  }
  let bars = span + MIN_HISTORY;
  let llmCapped = false;
  if (useLlm && bars > MIN_HISTORY + MAX_LLM_DECISIONS) {
    bars = MIN_HISTORY + MAX_LLM_DECISIONS;
    llmCapped = true;
  }
  const decisions = Math.max(1, bars - MIN_HISTORY);
  const estMinutes = useLlm
    ? Math.round(decisions * 0.5)
    : Math.max(1, Math.round(decisions / EST_DECISIONS_PER_SECOND / 60));
  return {
    bars,
    decisions,
    estMinutes,
    needsConfirm: useLlm || decisions > LARGE_RUN_DECISIONS,
    llmCapped,
  };
}
