/**
 * F2 - Pure derived views over ReducerState. No mutation, no side effects.
 */
import { laneOf } from "../domain/roles";
import { ROLE_REGISTRY } from "./model";
import type {
  ApplicationStatus,
  ArtifactRecord,
  ReducerState,
  Report,
  RoleCard,
  Turn,
} from "./model";

export type DebateStage = "research" | "risk";

export type DebateLaneId =
  | "bull"
  | "bear"
  | "aggressive"
  | "neutral"
  | "conservative";

export interface DebateLane {
  id: DebateLaneId;
  turns: Turn[];
}

export type DebateBlock =
  | {
      kind: "round";
      stage: DebateStage;
      index: number;
      lanes: DebateLane[];
    }
  | { kind: "verdict"; turn: Turn }
  | { kind: "linear"; turn: Turn };

const ACTOR_ORDER = new Map(
  ROLE_REGISTRY.map((role, index) => [role.actor_id, index]),
);

const LANE_ORDER: Record<DebateStage, readonly DebateLaneId[]> = {
  research: ["bull", "bear"],
  risk: ["aggressive", "neutral", "conservative"],
};

function compareTurns(left: Turn, right: Turn): number {
  return (
    left.turn_index - right.turn_index ||
    (ACTOR_ORDER.get(left.actor_id) ?? Number.MAX_SAFE_INTEGER) -
      (ACTOR_ORDER.get(right.actor_id) ?? Number.MAX_SAFE_INTEGER) ||
    left.turn_id.localeCompare(right.turn_id)
  );
}

function actorsForFilter(filter?: string): Set<string> | null {
  if (!filter || filter === "all") return null;
  return new Set(
    ROLE_REGISTRY.filter((role) => role.team_id === filter).map(
      (role) => role.actor_id,
    ),
  );
}

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
 * Turns in deterministic turn/role order. If filter is a team_id, keep only
 * turns whose actor_id belongs to a role in that team; 'all' or undefined
 * returns every turn.
 */
export function turnTimeline(state: ReducerState, filter?: string): Turn[] {
  const actorsInTeam = actorsForFilter(filter);
  return Object.values(state.turns)
    .filter((turn) => !actorsInTeam || actorsInTeam.has(turn.actor_id))
    .sort(compareTurns);
}

/**
 * Project turns into the transcript's structural reading order.
 *
 * Debate roles are grouped by their recorded turn_index, never by event/object
 * arrival order. Non-adversarial roles remain linear and judging roles become
 * full-width verdict blocks after the rounds they resolve.
 */
export function debateScript(
  state: ReducerState,
  filter?: string,
): DebateBlock[] {
  const actorsInTeam = actorsForFilter(filter);
  const turns = Object.values(state.turns).filter(
    (turn) => !actorsInTeam || actorsInTeam.has(turn.actor_id),
  );
  const linear: Turn[] = [];
  const verdicts = new Map<DebateStage, Turn[]>();
  const rounds: Record<DebateStage, Map<number, Map<DebateLaneId, Turn[]>>> = {
    research: new Map(),
    risk: new Map(),
  };

  for (const turn of turns) {
    const assignment = laneOf(turn.actor_id);
    if (!assignment) {
      linear.push(turn);
      continue;
    }
    if (assignment.lane === "judge") {
      const stageVerdicts = verdicts.get(assignment.stage) ?? [];
      stageVerdicts.push(turn);
      verdicts.set(assignment.stage, stageVerdicts);
      continue;
    }

    const stage = assignment.stage;
    const lane = assignment.lane as DebateLaneId;
    const byLane = rounds[stage].get(turn.turn_index) ?? new Map();
    const laneTurns = byLane.get(lane) ?? [];
    laneTurns.push(turn);
    byLane.set(lane, laneTurns);
    rounds[stage].set(turn.turn_index, byLane);
  }

  const blocks: DebateBlock[] = [];
  const appendLinearForActors = (actorIds: readonly string[]) => {
    const allowed = new Set(actorIds);
    linear
      .filter((turn) => allowed.has(turn.actor_id))
      .sort(compareTurns)
      .forEach((turn) => blocks.push({ kind: "linear", turn }));
  };
  const appendStage = (stage: DebateStage) => {
    const stageRounds = [...rounds[stage].entries()].sort(
      ([left], [right]) => left - right,
    );
    for (const [index, byLane] of stageRounds) {
      const lanes: DebateLane[] = LANE_ORDER[stage].flatMap((lane) => {
        const laneTurns = byLane.get(lane);
        return laneTurns
          ? [{ id: lane, turns: [...laneTurns].sort(compareTurns) }]
          : [];
      });
      blocks.push({ kind: "round", stage, index, lanes });
    }
    (verdicts.get(stage) ?? [])
      .sort(compareTurns)
      .forEach((turn) => blocks.push({ kind: "verdict", turn }));
  };

  appendLinearForActors([
    "analyst.market",
    "analyst.sentiment",
    "analyst.news",
    "analyst.fundamentals",
    "evidence.steward",
  ]);
  appendStage("research");
  appendLinearForActors(["trader"]);
  appendStage("risk");

  return blocks;
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

/** Artifacts linked to the selected turn through input/report events. */
export function artifactsForTurn(
  state: ReducerState,
  turn_id: string,
): ArtifactRecord[] {
  return Object.values(state.artifacts).filter((a) => a.turn_id === turn_id);
}

export type FinalReportResolution =
  | { status: "ready"; artifact_id: string; source: "explicit" | "legacy_locator" }
  | { status: "missing" }
  | { status: "ambiguous"; artifact_ids: string[] };

/**
 * Resolve the canonical complete report without guessing from arbitrary
 * Markdown. New runs supply an explicit artifact id; historical runs only
 * receive a compatibility fallback when exactly one canonical locator exists.
 */
export function finalReportResolution(
  state: ReducerState,
): FinalReportResolution {
  const explicit = state.meta.final_report_artifact_id;
  if (explicit) {
    return { status: "ready", artifact_id: explicit, source: "explicit" };
  }
  const matches = Object.values(state.artifacts)
    .filter((artifact) => artifact.locator === "reports/complete_report.md")
    .map((artifact) => artifact.artifact_id);
  if (matches.length === 1) {
    return {
      status: "ready",
      artifact_id: matches[0],
      source: "legacy_locator",
    };
  }
  if (matches.length > 1) {
    return { status: "ambiguous", artifact_ids: matches };
  }
  return { status: "missing" };
}
