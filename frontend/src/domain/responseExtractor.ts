/**
 * G2 - Pure extraction of a role's current response/decision text from the
 * business_delta artifact payload.
 *
 * The turn.output_ready artifact is the JSON-serialized AgentState delta the
 * role node wrote (NOT a standalone response blob). The timeline must walk
 * the delta per-actor to surface the right field. Field paths verified
 * against tradingagents/agents/utils/agent_states.py.
 */

export interface ExtractedResponse {
  text: string | null;
  badge: string | null;
}

/**
 * actor_id -> dotted path into the business_delta for the role's primary
 * response/decision text. For documentation; extractResponse implements the
 * actual defensive walk.
 */
export const RESPONSE_FIELD_MAP: Record<string, string> = {
  "analyst.market": "market_report",
  "analyst.sentiment": "sentiment_report",
  "analyst.news": "news_report",
  "analyst.fundamentals": "fundamentals_report",
  "evidence.steward": "evidence_report",
  "researcher.bull": "investment_debate_state.current_response",
  "researcher.bear": "investment_debate_state.current_response",
  "manager.research": "investment_debate_state.judge_decision",
  trader: "trader_investment_plan",
  "risk.aggressive": "risk_debate_state.current_aggressive_response",
  "risk.neutral": "risk_debate_state.current_neutral_response",
  "risk.conservative": "risk_debate_state.current_conservative_response",
  "manager.portfolio": "final_trade_decision",
};

/** Defensive dotted-path reader; returns undefined if any segment is missing. */
function readPath(delta: unknown, dotted: string): unknown {
  if (delta === null || delta === undefined) return undefined;
  if (typeof delta !== "object" || Array.isArray(delta)) return undefined;
  const parts = dotted.split(".");
  let cursor: unknown = delta;
  for (const part of parts) {
    if (cursor === null || cursor === undefined) return undefined;
    if (typeof cursor !== "object" || Array.isArray(cursor)) return undefined;
    cursor = (cursor as Record<string, unknown>)[part];
  }
  return cursor;
}

function asString(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/**
 * Walks the delta per the extraction map and returns { text, badge }.
 * - text: the role's current response/decision string.
 * - badge: optional secondary label (evidence_status for evidence.steward;
 *   risk_debate_state.judge_decision for manager.portfolio if present).
 *
 * Returns { text: null, badge: null } if the field is absent or not a string.
 * Defensive: delta may be partial, nested objects may be missing.
 */
export function extractResponse(
  actor_id: string,
  delta: Record<string, unknown>,
): ExtractedResponse {
  const path = RESPONSE_FIELD_MAP[actor_id];
  if (!path) {
    return { text: null, badge: null };
  }
  const text = asString(readPath(delta, path));

  let badge: string | null = null;
  if (actor_id === "evidence.steward") {
    badge = asString(readPath(delta, "evidence_status"));
  } else if (actor_id === "manager.portfolio") {
    badge = asString(readPath(delta, "risk_debate_state.judge_decision"));
  }

  return { text, badge };
}
