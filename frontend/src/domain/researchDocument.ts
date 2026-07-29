import { ROLE_LABELS_ZH } from "./roles";
import { ROLE_REGISTRY } from "../state/model";
import type { ReducerState, Turn, TurnStatus } from "../state/model";

export type ResearchEntryStatus = "waiting" | "candidate" | "committed" | TurnStatus;
export type ResearchArtifactKind = "report" | "business_delta" | null;

export interface ResearchEntry {
  actor_id: string;
  label: string;
  turn_id: string | null;
  turn_index: number | null;
  status: ResearchEntryStatus;
  artifact_id: string | null;
  artifact_kind: ResearchArtifactKind;
  reason?: string;
}

export interface DebateRound {
  round: number;
  bull: ResearchEntry;
  bear: ResearchEntry;
}

export interface RiskRound {
  round: number;
  aggressive: ResearchEntry;
  conservative: ResearchEntry;
  neutral: ResearchEntry;
}

export interface ResearchDocumentModel {
  analysts: ResearchEntry[];
  evidence: ResearchEntry;
  debate_rounds: DebateRound[];
  research_verdict: ResearchEntry;
  trading_plan: ResearchEntry;
  risk_rounds: RiskRound[];
  portfolio_verdict: ResearchEntry;
}

const REPORT_KIND_BY_ACTOR: Readonly<Record<string, string>> = {
  "analyst.market": "market",
  "analyst.sentiment": "sentiment",
  "analyst.news": "news",
  "analyst.fundamentals": "fundamentals",
  trader: "trader",
  "manager.portfolio": "portfolio",
};

function turnsForActor(state: ReducerState, actor_id: string): Turn[] {
  return Object.values(state.turns)
    .filter((turn) => turn.actor_id === actor_id)
    .sort((left, right) => left.turn_index - right.turn_index);
}

function latestTurn(state: ReducerState, actor_id: string): Turn | null {
  const turns = turnsForActor(state, actor_id);
  return turns.length > 0 ? turns[turns.length - 1] : null;
}

function graphTaskForTurn(state: ReducerState, turn: Turn) {
  if (turn.graph_task_id) return state.graph_tasks[turn.graph_task_id];
  return Object.values(state.graph_tasks).find(
    (task) => task.observation_commit?.turn_id === turn.turn_id,
  );
}

function isCommitted(state: ReducerState, turn: Turn): boolean {
  if (turn.status !== "completed") return false;
  const task = graphTaskForTurn(state, turn);
  // Old event logs predate graph tasks.  A terminal turn is their strongest
  // available commitment boundary; new logs additionally require applied=true.
  return task === undefined || task.applied;
}

function canonicalReportArtifact(state: ReducerState, turn: Turn): string | null {
  const kind = REPORT_KIND_BY_ACTOR[turn.actor_id];
  if (!kind) return null;
  const reports = state.reports
    .filter((report) => report.turn_id === turn.turn_id && report.report_kind === kind)
    .sort((left, right) => right.revision - left.revision);
  return reports[0]?.artifact_id ?? null;
}

function waitingEntry(actor_id: string, round: number | null = null): ResearchEntry {
  return {
    actor_id,
    label: ROLE_LABELS_ZH[actor_id] ?? actor_id,
    turn_id: null,
    turn_index: round,
    status: "waiting",
    artifact_id: null,
    artifact_kind: null,
  };
}

function entryForTurn(
  state: ReducerState,
  actor_id: string,
  turn: Turn | null,
  round: number | null = null,
): ResearchEntry {
  if (!turn) return waitingEntry(actor_id, round);
  const committed = isCommitted(state, turn);
  const reportArtifact = committed ? canonicalReportArtifact(state, turn) : null;
  const taskArtifact = committed
    ? graphTaskForTurn(state, turn)?.business_delta_artifact_id ?? turn.artifact_id ?? null
    : turn.artifact_id ?? null;
  return {
    actor_id,
    label: ROLE_LABELS_ZH[actor_id] ?? actor_id,
    turn_id: turn.turn_id,
    turn_index: turn.turn_index,
    status: committed ? "committed" : turn.status,
    artifact_id: reportArtifact ?? taskArtifact,
    artifact_kind: reportArtifact ? "report" : taskArtifact ? "business_delta" : null,
    reason: turn.reason,
  };
}

function roundsFor(
  state: ReducerState,
  actors: readonly string[],
): number[] {
  const rounds = new Set<number>();
  for (const actor_id of actors) {
    for (const turn of turnsForActor(state, actor_id)) rounds.add(turn.turn_index);
  }
  return [...rounds].sort((left, right) => left - right);
}

function turnForRound(
  state: ReducerState,
  actor_id: string,
  round: number,
): Turn | null {
  return turnsForActor(state, actor_id).find((turn) => turn.turn_index === round) ?? null;
}

/** Pure research-reading projection shared by SSE, refresh, history, and resume. */
export function buildResearchDocument(state: ReducerState): ResearchDocumentModel {
  const analysts = ROLE_REGISTRY.filter(
    (role) => role.analyst_key !== null && state.meta.selected_analysts.includes(role.analyst_key),
  ).map((role) => entryForTurn(state, role.actor_id, latestTurn(state, role.actor_id)));

  const debateRounds = roundsFor(state, ["researcher.bull", "researcher.bear"]).map(
    (round) => ({
      round,
      bull: entryForTurn(state, "researcher.bull", turnForRound(state, "researcher.bull", round), round),
      bear: entryForTurn(state, "researcher.bear", turnForRound(state, "researcher.bear", round), round),
    }),
  );
  const riskRounds = roundsFor(state, [
    "risk.aggressive",
    "risk.conservative",
    "risk.neutral",
  ]).map((round) => ({
    round,
    aggressive: entryForTurn(state, "risk.aggressive", turnForRound(state, "risk.aggressive", round), round),
    conservative: entryForTurn(state, "risk.conservative", turnForRound(state, "risk.conservative", round), round),
    neutral: entryForTurn(state, "risk.neutral", turnForRound(state, "risk.neutral", round), round),
  }));

  return {
    analysts,
    evidence: entryForTurn(state, "evidence.steward", latestTurn(state, "evidence.steward")),
    debate_rounds: debateRounds,
    research_verdict: entryForTurn(state, "manager.research", latestTurn(state, "manager.research")),
    trading_plan: entryForTurn(state, "trader", latestTurn(state, "trader")),
    risk_rounds: riskRounds,
    portfolio_verdict: entryForTurn(state, "manager.portfolio", latestTurn(state, "manager.portfolio")),
  };
}
