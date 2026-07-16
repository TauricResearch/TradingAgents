/** What-if position planner (review P2.1): sizing math for the USER'S OWN
 * hypothetical trade drawn with the long/short chart tool. This is a
 * planning calculator over user-chosen levels — clearly not platform
 * advice and not pipeline output. Mirrors the backend's
 * fixed_risk_position_size (analytics/risk.py): size so entry→stop loses
 * exactly riskPct of equity, capped by maxPositionPct of equity notional. */

export interface PositionPlanInput {
  side: "long" | "short";
  entry: number;
  stop: number;
  target: number;
  equity: number;
  riskPct: number; // % of equity risked entry→stop (default 1)
  maxPositionPct?: number; // notional cap as % of equity (default 10)
}

export interface PositionPlan {
  valid: boolean;
  reason?: string;
  quantity: number;
  notional: number;
  pctOfEquity: number;
  riskAmount: number; // account currency lost at the stop
  rewardAmount: number; // account currency gained at the target
  rr: number;
  breakevenWinRate: number; // fraction, from R:R
  capped: boolean; // notional cap reduced the size (risk < riskPct)
}

export function computePositionPlan(input: PositionPlanInput): PositionPlan {
  const { side, entry, stop, target, equity, riskPct } = input;
  const maxPositionPct = input.maxPositionPct ?? 10;
  const invalid = (reason: string): PositionPlan => ({
    valid: false, reason, quantity: 0, notional: 0, pctOfEquity: 0,
    riskAmount: 0, rewardAmount: 0, rr: 0, breakevenWinRate: 0, capped: false,
  });
  if (!(entry > 0) || !(stop > 0) || !(target > 0)) return invalid("levels must be positive");
  if (!(equity > 0)) return invalid("equity must be positive");
  if (!(riskPct > 0) || riskPct > 100) return invalid("risk % must be in (0, 100]");
  if (side === "long" && !(stop < entry && target > entry))
    return invalid("long needs stop below entry and target above");
  if (side === "short" && !(stop > entry && target < entry))
    return invalid("short needs stop above entry and target below");

  const perUnitRisk = Math.abs(entry - stop);
  const perUnitReward = Math.abs(target - entry);
  let quantity = (equity * riskPct) / 100 / perUnitRisk;
  const notionalCap = (equity * maxPositionPct) / 100;
  const capped = quantity * entry > notionalCap;
  // mirror of the engine's cap headroom (R2.8): at-cap sizes must survive
  // equity drift between sizing and the execution validator
  if (capped) quantity = (notionalCap * 0.99) / entry;
  const notional = quantity * entry;
  const rr = perUnitReward / perUnitRisk;
  return {
    valid: true,
    quantity,
    notional,
    pctOfEquity: (notional / equity) * 100,
    riskAmount: quantity * perUnitRisk,
    rewardAmount: quantity * perUnitReward,
    rr,
    breakevenWinRate: 1 / (1 + rr),
    capped,
  };
}
