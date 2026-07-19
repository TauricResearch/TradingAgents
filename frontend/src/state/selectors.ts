/**
 * F2 - Pure derived views over ReducerState. No mutation, no side effects.
 */
import { ROLE_REGISTRY } from "./model";
import type {
  ApplicationStatus,
  ArtifactRecord,
  ReducerState,
  Report,
  RoleCard,
  Turn,
} from "./model";

/** Roles present in state.roles, ordered by ROLE_REGISTRY. */
export function roleList(state: ReducerState): RoleCard[] {
  const out: RoleCard[] = [];
  for (const def of ROLE_REGISTRY) {
    const card = state.roles[def.actor_id];
    if (card) out.push(card);
  }
  return out;
}

/**
 * Turns in insertion order (JS string-key object order). If filter is a
 * team_id, keep only turns whose actor_id belongs to a role in that team;
 * 'all' or undefined returns every turn.
 */
export function turnTimeline(state: ReducerState, filter?: string): Turn[] {
  const turns = Object.values(state.turns);
  if (!filter || filter === "all") return turns;
  const actorsInTeam = new Set(
    ROLE_REGISTRY.filter((r) => r.team_id === filter).map((r) => r.actor_id),
  );
  return turns.filter((t) => actorsInTeam.has(t.actor_id));
}

export function currentRunStatus(state: ReducerState): ApplicationStatus {
  return state.meta.status;
}

export function reportsByKind(state: ReducerState, kind: string): Report[] {
  return state.reports.filter((r) => r.report_kind === kind);
}

export function isTerminal(state: ReducerState): boolean {
  const s = state.meta.status;
  return (
    s === "completed" ||
    s === "failed" ||
    s === "cancelled" ||
    s === "interrupted"
  );
}

/**
 * GAP: ArtifactRecord has no turn_ids link in model.ts, so we cannot join
 * artifacts back to a turn here. Returns [] until G3 adds the join.
 */
export function artifactsForTurn(
  state: ReducerState,
  turn_id: string,
): ArtifactRecord[] {
  void state;
  void turn_id;
  return [];
}