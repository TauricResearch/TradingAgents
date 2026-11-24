// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The terminal transcript as state: a pure fold over engine events, so what the screen shows can be
 * tested without a terminal.
 *
 * Finished blocks are final and append-only: the UI writes them once into the scrollback, in the
 * order things happened. Only the live region (the text being streamed, what is running, the status
 * line) is redrawn.
 */
import {
  AGENT_TOOL,
  ASK_TOOL,
  carriesOut,
  citedIds,
  type EventEnvelope,
  message,
  NOTICE,
  numberCitations,
  type Preview,
  type Source,
  type Usage,
} from "../contracts/index.js";
import type { Link } from "./links.js";
import type { List } from "./list.js";
import { openFence, stableSplit } from "./stream-split.js";

/** A finished block as appended: `gap` is the blank rows before it, owned by the block that follows. */
export type Block = BlockBody & { gap: number };

type BlockBody =
  /** The welcome block, written once before anything else; `news`: its one line of news, if any. */
  | { id: string; kind: "header"; version: string; model: string; keyed: boolean; news?: string }
  | { id: string; kind: "question"; text: string }
  /** Lines a command wrote (its output), shown as one quiet block; `links` on a row of their own after them. */
  | { id: string; kind: "lines"; lines: string[]; links?: Link[] }
  /** A list a command showed (/help, /skills): sections of aligned rows; `links` after them. */
  | { id: string; kind: "list"; list: List; links?: Link[] }
  /** What the answer cited, as the engine numbered it. */
  | { id: string; kind: "sources"; sources: Source[] }
  /**
   * `joined`: a part of an answer that continues the part before it with no gap (a code block cut in two).
   * `lead`: the first part of an answer item (nothing of the answer right before it): it carries the mark.
   */
  | { id: string; kind: "message"; text: string; joined?: boolean; lead?: boolean }
  | {
      id: string;
      kind: "tool";
      name: string;
      /** The call's arguments in a few words. */
      label?: string;
      summary: string;
      nested: boolean;
      source?: string;
      failed?: boolean;
      /** How long the call took. */
      elapsedMs?: number;
      /** The sub-agent that made it, for a nested call. */
      agent?: string;
      /** A few rows of what came back (preview.ts). */
      preview?: Preview;
    }
  /**
   * Sub-agents that ran together (one, or several at once), once the last of them ended: one row each under
   * a header saying how they went (a single agent is a row of its own).
   */
  | { id: string; kind: "agents"; members: AgentMember[]; elapsedMs?: number }
  /** `context`: about the model's context (earlier turns summarized, old results set aside), marked as such. */
  | { id: string; kind: "notice"; level: "info" | "warn" | "error"; text: string; context?: true }
  /** A step's data calls, three or more, once all were done: each call and how it went. */
  | { id: string; kind: "group"; calls: GroupedCall[]; elapsedMs?: number }
  /**
   * The main agent's thinking, once it ended: how long it took and all it thought (for the full transcript);
   * `lines`, what the scrollback keeps of it, its first and last lines; `omitted`, how many came between.
   */
  | { id: string; kind: "thought"; durationMs: number; text: string; lines?: string[]; omitted?: number }
  /** The line that closes a completed turn: what it took, and what it answered (for a report). */
  | {
      id: string;
      kind: "turnEnd";
      answered: Answered;
      durationMs: number;
      inputTokens: number;
      outputTokens: number;
      plan?: { done: number; total: number };
    };

/**
 * A completed turn as the engine ended it: its session, question (and whether it was asked in plan mode), the
 * final answer with its citations numbered as `sources` number them, the model the session ran on, and when.
 */
export type Answered = {
  session: string;
  question: string;
  plan?: true;
  answer: string;
  sources: Source[];
  model?: string;
  at: string;
};

/** One call of a group: what it was, and what came of it (or why it failed). */
export type GroupedCall = {
  name: string;
  label?: string;
  summary?: string;
  source?: string;
  failed?: boolean;
  reason?: string;
  elapsedMs?: number;
  preview?: Preview;
};

/**
 * The sources a group's calls were answered by, in the order first used: a call that failed answered
 * nothing, and a source named after others failed ("Yahoo, after Tauric failed") counts as itself.
 */
export function groupSources(calls: readonly GroupedCall[]): string[] {
  const named = calls.flatMap((call) =>
    !call.failed && call.source ? [call.source.split(", after ")[0]?.trim() ?? ""] : [],
  );
  return [...new Set(named.filter(Boolean))];
}

/**
 * The main agent's data calls of the step under way: the calls in the order made, whether something that is not
 * data was called beside them (then they stay rows of their own), and the results held until all are in.
 */
type Batch = { calls: string[]; mixed: boolean; held: Map<string, ToolBlock> };
type ToolBlock = Extract<BlockBody, { kind: "tool" }>;

/** Fewer data calls than this in a step stay rows of their own. */
const GROUP_MIN = 3;

/**
 * A tool call, keyed by the run that made it: call ids are unique only within one run. `startedAt`: when
 * this terminal saw it start, for the time shown.
 */
type RunningTool = {
  run: string;
  call: string;
  name: string;
  nested: boolean;
  label?: string;
  startedAt: number;
  /** When the engine said it started, for the time it took (correct for a replayed session too). */
  startedTs?: number;
};
/**
 * A sub-agent and how it went. `label`: as people see it called ("Equity Research"); `agent`: its name in the
 * catalog ("equity"), which picks its colour; `title`: the few words its row shows (the main agent gives them
 * with the brief); `summary`: the gist of its report (for the full transcript).
 * `stopped`: the person stopped it (no reason); `capped`: it stopped at a limit, with what it had.
 */
export type AgentMember = {
  label: string;
  agent: string;
  title?: string;
  summary: string;
  status: "done" | "failed" | "stopped" | "capped";
  reason?: string;
  calls?: number;
  elapsedMs?: number;
  /** Its calls that failed, each as name and label, then the reason (for the full transcript). */
  failures?: string[];
  /** Its calls that came back, each as name and label, then the result (for the full transcript). */
  tools?: string[];
};

/**
 * A sub-agent of the group running now; `activity`: its latest call, as name and label; `finished`: how it
 * went, once it ended while others of its group still run.
 */
type RunningAgent = {
  run: string;
  /** The agent as people see it called. */
  label: string;
  /** Its name in the catalog, for its colour. */
  agent: string;
  title?: string;
  startedAt: number;
  startedTs?: number;
  activity?: string;
  finished?: AgentMember;
  /** A step of it is being asked for again: which retry, of how many (unknown in an older session). */
  retrying?: Retrying;
};

/** A model step asked for again, until the run's next event: which retry, of how many, when known. */
type Retrying = { attempt?: number; of?: number };

/** Tools that keep the main agent's own books (its plan, a skill read, its questions): not shown as rows. */
const BOOKKEEPING = new Set(["update_plan", "use_skill", ASK_TOOL]);
/** The main agent's memory: read and written, not fetched. */
const MEMORY = new Set(["recall_memory", "save_note", "record_decision"]);
/** A call that researches (data, compute, an agent), as against keeping the books: what an answer follows. */
const researches = (name: string) => !BOOKKEEPING.has(name) && !MEMORY.has(name) && name !== "evidence";

/** The state once `run` has gone on after a retry: what said it was being asked for again is gone. */
function resumed(state: TranscriptState, isMain: boolean, run: string): TranscriptState {
  if (isMain) {
    if (!state.live.retrying) return state;
    const { retrying: _, ...live } = state.live;
    return { ...state, live };
  }
  if (!state.live.agents.some((agent) => agent.run === run && agent.retrying)) return state;
  const agents = state.live.agents.map((agent) => {
    if (agent.run !== run) return agent;
    const { retrying: _, ...rest } = agent;
    return rest;
  });
  return { ...state, live: { ...state.live, agents } };
}

/** An envelope's time in milliseconds, when it has one. */
function timeOf(ts: string): number | undefined {
  const ms = Date.parse(ts);
  return Number.isFinite(ms) ? ms : undefined;
}

/** The engine's start time of something, when its envelope has one. */
function since(ts: string): { startedTs?: number } {
  const ms = timeOf(ts);
  return ms === undefined ? {} : { startedTs: ms };
}

/**
 * How long something took, from the engine's times when both are known (so a replayed session shows its
 * real times), else from when this terminal saw it start.
 */
function took(started: { startedAt: number; startedTs?: number }, ts: string): number {
  const end = timeOf(ts);
  return started.startedTs !== undefined && end !== undefined && end >= started.startedTs
    ? end - started.startedTs
    : Math.max(0, Date.now() - started.startedAt);
}
type PlanStep = { text: string; status: "pending" | "active" | "done" | "skipped" };

export type TranscriptState = {
  done: Block[];
  live: {
    /** The part of the main agent's answer not final yet; the rest is already in `done`. */
    text: string;
    /** When the main agent began thinking in the step under way (this terminal's clock). */
    thinkingSince?: number;
    /** When the engine said that thinking began, for the time it took (a replay's real time too). */
    thinkingStartTs?: number;
    /** What the main agent has thought since it began thinking. */
    reasoning: string;
    /** The code fence `text` is inside, its opening already written: it renders `text`. */
    fence?: string;
    /** How many parts of the answer under way are in `done`, for their ids. */
    parts: number;
    thinking: boolean;
    tools: RunningTool[];
    agents: RunningAgent[];
    /** The main agent's plan while its turn runs. */
    plan: PlanStep[];
    /** Data calls each running sub-agent has finished, shown as a count on its line when it ends. */
    calls: Record<string, number>;
    /** Each running sub-agent's failed calls, listed under its row when it ends. */
    failures: Record<string, string[]>;
    /** Each running sub-agent's calls that came back, for the full transcript. */
    results: Record<string, string[]>;
    /** The main agent's calls that started a sub-agent: their rows are the agents' (a failure too). */
    delegated: string[];
    /** The title each of the main agent's calls to a sub-agent gave it (what its row shows), by call. */
    titles: Record<string, string>;
    /** The main agent's data calls of the step under way. */
    batch?: Batch;
    /** Earlier turns are being summarized before the question's work starts. */
    compacting?: true;
    /** The main agent's step is being asked for again (the status row says so). */
    retrying?: Retrying;
  };
  /**
   * What the main agent streamed in the step under way and in the last finished step. A completed turn's
   * answer is added unless the final step already streamed it.
   */
  /**
   * The turn under way: its question, whether it was asked in plan mode, whether it asked the user, and the
   * text of its steps.
   */
  /**
   * `stepText`: the step under way; `sinceResearch`: what the finished steps wrote since the main agent's
   * last research call, which the turn's answer is made of.
   */
  /** `worked`: the main agent carried research out (computed, or ran an agent) in this turn. */
  turn: {
    question: string;
    plan?: true;
    asked?: true;
    worked?: true;
    stepText: string;
    sinceResearch: string;
  };
  /** The app wrote the question it just sent: the next `turn.started` does not write it again. */
  echoed?: boolean;
  /**
   * Citations: the ids of recorded results (any turn's), and the ones the turn's answer cited so far,
   * numbered by first appearance as the engine numbers them when the turn completes.
   */
  citations: { recorded: readonly string[]; cited: readonly Pick<Source, "id" | "n">[] };
  /**
   * The session whose last turn proposed a plan: asked in plan mode, completed, without asking the user or
   * carrying any research out (only lookups: see carriesOut), whatever it showed with update_plan. Until the
   * next question, the user can run it as it stands.
   */
  planReady?: string;
  /** `since`: when this terminal saw the running turn start, for the time shown while it runs. */
  status: { model?: string; usage?: Usage; turnActive: boolean; since?: number };
};

/** The event stream itself broke; not an engine event, so the UI can still close the transcript. */
export type StreamFailure = { type: "stream.failed"; message: string };
/** Something the UI itself has to say (a setting that is missing, say), outside any turn. */
type LocalNotice = { type: "local.notice"; level: "info" | "warn" | "error"; text: string };
/** The app wrote a question as it sent it; `local.unsent` when the engine then refused it. */
type LocalQuestion = { type: "local.question"; text: string } | { type: "local.unsent" };
/** A command's output. */
type LocalLines = { type: "local.lines"; lines: string[]; links?: Link[] };
type LocalList = { type: "local.list"; list: List; links?: Link[] };
/** The welcome block. */
type LocalHeader = {
  type: "local.header";
  version: string;
  model: string;
  keyed: boolean;
  news?: string | undefined;
};
export type LocalAction = StreamFailure | LocalNotice | LocalQuestion | LocalLines | LocalList | LocalHeader;

export const emptyTranscript: TranscriptState = {
  done: [],
  live: {
    text: "",
    parts: 0,
    thinking: false,
    reasoning: "",
    tools: [],
    agents: [],
    plan: [],
    calls: {},
    failures: {},
    results: {},
    delegated: [],
    titles: {},
  },
  turn: { question: "", stepText: "", sinceResearch: "" },
  citations: { recorded: [], cited: [] },
  status: { turnActive: false },
};

/**
 * The blank rows before `block`, after `previous`: one before a question (none under the header), one
 * between blocks of different kinds, none between rows of a kind that sit together (tool and agent rows,
 * notices, a code block cut in two). The header owns the blank row after it, and a question the rows
 * above and below its text.
 */
export function gapBefore(
  previous: Block | undefined,
  block: BlockBody | { kind: "message" | "thought" },
): number {
  // Two questions in a row (a turn that never answered, replayed) keep a row between their blocks.
  if (previous?.kind === "question" && block.kind === "question") return 1;
  if (!previous || previous.kind === "header" || previous.kind === "question") return 0;
  switch (block.kind) {
    case "header":
      return 0;
    case "question":
      return 1;
    case "message":
      // A part continues the part before it only when nothing came between.
      return "joined" in block && block.joined && previous.kind === "message" ? 0 : 1;
    case "tool":
    case "group":
      // Each step's calls are a block of their own: a solo call, or a step's calls as one group.
      return 1;
    case "agents":
      // Agents are a block of their own.
      return 1;
    case "notice":
      // Notices of one kind (retries of one request) stay together; others are blocks of their own.
      return previous.kind === "notice" && previous.level === block.level ? 0 : 1;
    case "thought":
      return 1;
    case "turnEnd":
      return 1;
    case "lines":
    case "list":
      return 1;
    case "sources":
      return 1;
  }
}

/**
 * Append a finished block with its spacing. Results held for a group go out first, as rows of their own:
 * something came between them, so they are not folded.
 */
function push(state: TranscriptState, block: BlockBody): TranscriptState {
  const batch = state.live.batch;
  if (batch?.held.size) {
    let flushed: TranscriptState = {
      ...state,
      live: { ...state.live, batch: { ...batch, mixed: true, held: new Map() } },
    };
    for (const call of batch.calls) {
      const held = batch.held.get(call);
      if (held) flushed = place(flushed, held);
    }
    return place(flushed, block);
  }
  return place(state, block);
}

function place(state: TranscriptState, block: BlockBody): TranscriptState {
  const previous = state.done.at(-1);
  const gap = gapBefore(previous, block);
  const lead = block.kind === "message" && previous?.kind !== "message" ? { lead: true } : {};
  return { ...state, done: [...state.done, { ...block, ...lead, gap } as Block] };
}

/**
 * `citations` with the recorded ids `text` cites added, numbered by first appearance: the engine's rule,
 * so the numbers written while the answer streams are the ones its sources carry at the end.
 */
function noteCited(citations: TranscriptState["citations"], text: string): TranscriptState["citations"] {
  const fresh = citedIds(text, (id) => citations.recorded.includes(id)).filter(
    (id) => citations.recorded.includes(id) && !citations.cited.some((cited) => cited.id === id),
  );
  if (!fresh.length) return citations;
  const cited = [...citations.cited];
  for (const id of fresh) cited.push({ id, n: cited.length + 1 });
  return { ...citations, cited };
}

/** The live text as Markdown that renders on its own: inside the code block it continues, if any. */
export function liveMarkdown(live: TranscriptState["live"]): string {
  return live.fence ? `${live.fence}\n${live.text}` : live.text;
}

/** A part of the answer as a finished block: the first part, or one continuing the part before it. */
function part(state: TranscriptState, id: string, text: string, joined: boolean): BlockBody {
  return {
    id: state.live.parts ? `${id}:part${state.live.parts}` : `${id}:text`,
    kind: "message",
    // Citations as people read them; the text was noted as it streamed.
    text: numberCitations(text, state.citations.cited),
    ...(joined ? { joined } : {}),
  };
}

/** Blank lines (spaces and tabs only) at the start of `text`. */
const LEADING_BLANK = /^(?:[ \t]*\n)+/;

/** The thinking under way as the live region shows it: without the blank lines it began with. */
export function pendingThought(live: TranscriptState["live"]): string {
  return live.reasoning.replace(LEADING_BLANK, "");
}

/**
 * What the scrollback keeps of a thought that ended: its first and last lines that are not blank, and how
 * many lines came between (the whole of it goes to the transcript written out, /export).
 */
function collapsed(reasoning: string): { lines: string[]; omitted?: number } | undefined {
  const lines = reasoning.split("\n").filter((line) => line.trim());
  if (!lines.length) return undefined;
  if (lines.length <= 2) return { lines };
  return { lines: [lines[0] as string, lines.at(-1) as string], omitted: lines.length - 2 };
}

/**
 * End the main agent's thinking, if it was thinking: its first and last lines go to the scrollback, then one
 * line saying how long it took (from the engine's times when both are known, else this terminal's),
 * carrying what it thought (nothing, for a resumed session, which keeps only that it thought).
 */
function closeThought(state: TranscriptState, id: string, ts: string): TranscriptState {
  if (!state.live.thinking) return state;
  const kept = collapsed(state.live.reasoning);
  const { thinkingSince, thinkingStartTs, reasoning, ...live } = state.live;
  const end = timeOf(ts);
  const durationMs =
    thinkingStartTs !== undefined && end !== undefined && end >= thinkingStartTs
      ? end - thinkingStartTs
      : Math.max(0, Date.now() - (thinkingSince ?? Date.now()));
  const next = { ...state, live: { ...live, thinking: false, reasoning: "" } };
  return push(next, { id: `${id}:thought`, kind: "thought", durationMs, text: reasoning, ...kept });
}

/**
 * Move the text streamed so far into a finished message block, exactly as streamed. Within a step (a
 * notice arriving mid-answer), a code block the text ends in stays open for the text after it.
 */
function flushText(state: TranscriptState, id: string, withinStep = false): TranscriptState {
  // Thinking is not the text's to end: closeThought does that.
  const { fence, ...rest } = state.live;
  if (!state.live.text.trim()) {
    // Nothing to write: within a step the answer's place is kept; after it, the answer is over.
    return {
      ...state,
      live: withinStep ? { ...rest, ...(fence ? { fence } : {}) } : { ...rest, text: "", parts: 0 },
    };
  }
  const open = withinStep ? openFence(state.live.text, fence) : undefined;
  const block = part(state, id, liveMarkdown(state.live), fence !== undefined);
  const live = {
    ...rest,
    text: "",
    parts: withinStep ? state.live.parts + 1 : 0,
    ...(open ? { fence: open } : {}),
  };
  // What pushing changed of the batch (results it sent out) is kept.
  const pushed = push(state, block);
  return { ...pushed, live: { ...live, ...(pushed.live.batch ? { batch: pushed.live.batch } : {}) } };
}

/**
 * Write the final head of the text streamed so far into the scrollback, where it stays as it is:
 * the live region keeps only what may still change, so no part of a long answer is out of sight.
 */
function commitStable(state: TranscriptState, id: string): TranscriptState {
  // A cut can leave another behind it (a code block closed with nothing in it, then a paragraph).
  for (let next = commitOnce(state, id); next !== state; next = commitOnce(state, id)) state = next;
  return state;
}

function commitOnce(state: TranscriptState, id: string): TranscriptState {
  const split = stableSplit(state.live.text, state.live.fence);
  if (!split) return state;
  const { fence: _, ...live } = state.live;
  const next = {
    ...live,
    text: split.rest,
    ...(split.restFence ? { fence: split.restFence } : {}),
  };
  if (!split.head.trim()) return { ...state, live: next };
  const block = part(state, id, split.head, state.live.fence !== undefined);
  const pushed = push(state, block);
  return {
    ...pushed,
    live: {
      ...next,
      parts: state.live.parts + 1,
      ...(pushed.live.batch ? { batch: pushed.live.batch } : {}),
    },
  };
}

/** Append a finished block after whatever text came before it. */
function append(state: TranscriptState, id: string, block: BlockBody): TranscriptState {
  return push(flushText(state, id, state.status.turnActive), block);
}

/** Results held for a group, out as rows of their own (a turn ended before all were in). */
function release(state: TranscriptState): TranscriptState {
  const batch = state.live.batch ?? { calls: [], mixed: true, held: new Map<string, ToolBlock>() };
  let next: TranscriptState = {
    ...state,
    live: { ...state.live, batch: { ...batch, mixed: true, held: new Map() } },
  };
  for (const call of batch.calls) {
    const held = batch.held.get(call);
    if (held) next = place(next, held);
  }
  // A sub-agent the turn left running keeps its failed calls: rows of their own.
  for (const [run, failures] of Object.entries(next.live.failures)) {
    for (const [index, failure] of failures.entries()) {
      next = place(next, {
        id: `u:failed:${run}:${index}:${next.done.length}`,
        kind: "tool",
        name: message("app.someTool"),
        summary: failure,
        nested: true,
        failed: true,
      });
    }
  }
  return { ...next, live: { ...next.live, failures: {} } };
}

/** End the turn: keep what was streamed, record how it ended, clear what was running. */
/**
 * Write the group of sub-agents: each as it ended, in the order they started; one still running when the turn
 * ended (`ts`) was stopped with it.
 */
function closeAgents(state: TranscriptState, id: string, ts?: string): TranscriptState {
  const { agents } = state.live;
  if (!agents.length) return state;
  const members = agents.map(
    (agent): AgentMember =>
      agent.finished ?? {
        label: agent.label,
        agent: agent.agent,
        ...(agent.title ? { title: agent.title } : {}),
        summary: "",
        status: "stopped",
        ...(state.live.calls[agent.run] ? { calls: state.live.calls[agent.run] } : {}),
        elapsedMs: ts ? took(agent, ts) : Math.max(0, Date.now() - agent.startedAt),
        ...(state.live.failures[agent.run]?.length ? { failures: state.live.failures[agent.run] } : {}),
        ...(state.live.results[agent.run]?.length ? { tools: state.live.results[agent.run] } : {}),
      },
  );
  const runs = new Set(agents.map((agent) => agent.run));
  const keep = <T>(record: Record<string, T>) =>
    Object.fromEntries(Object.entries(record).filter(([key]) => !runs.has(key)));
  const cleared = {
    ...state,
    live: {
      ...state.live,
      agents: [],
      tools: state.live.tools.filter((tool) => !runs.has(tool.run)),
      calls: keep(state.live.calls),
      failures: keep(state.live.failures),
      results: keep(state.live.results),
    },
  };
  const elapsed = members.map((member) => member.elapsedMs ?? 0);
  return append(cleared, `${id}:agents`, {
    id: `${id}:agents`,
    kind: "agents",
    members,
    ...(elapsed.some(Boolean) ? { elapsedMs: Math.max(...elapsed) } : {}),
  });
}

function endTurn(state: TranscriptState, id: string, ts: string, end?: BlockBody): TranscriptState {
  const closed = flushText(closeThought(closeAgents(state, id, ts), id, ts), id);
  const released = release(closed);
  const flushed = end ? push(released, end) : released;
  return {
    ...flushed,
    live: (({ batch: _, compacting: _compacting, retrying: _retrying, ...rest }) => ({
      ...rest,
      tools: [],
      agents: [],
      plan: [],
      calls: {},
      failures: {},
      results: {},
      delegated: [],
      titles: {},
    }))(flushed.live),
    // A step left open by the end is over too: nothing is being written now.
    turn: { ...flushed.turn, stepText: "" },
    status: { ...flushed.status, turnActive: false },
  };
}

export function reduceTranscript(
  state: TranscriptState,
  action: EventEnvelope | LocalAction,
): TranscriptState {
  if ("type" in action) {
    // Engine blocks are "e:"-prefixed, so these ids cannot meet one of theirs.
    const id = `u:${state.done.length}`;
    switch (action.type) {
      case "local.notice":
        return push(state, { id, kind: "notice", level: action.level, text: action.text });
      case "local.lines":
        return push(state, {
          id,
          kind: "lines",
          lines: action.lines,
          ...(action.links?.length ? { links: action.links } : {}),
        });
      case "local.list":
        return push(state, {
          id,
          kind: "list",
          list: action.list,
          ...(action.links?.length ? { links: action.links } : {}),
        });
      case "local.header":
        return push(state, {
          id,
          kind: "header",
          version: action.version,
          model: action.model,
          keyed: action.keyed,
          ...(action.news ? { news: action.news } : {}),
        });
      case "local.question":
        return { ...push(state, { id, kind: "question", text: action.text }), echoed: true };
      case "local.unsent": {
        const { echoed: _, ...rest } = state;
        return rest;
      }
    }
    return endTurn(state, id, "", { id, kind: "notice", level: "error", text: action.message });
  }
  const envelope = action;
  const { event } = envelope;
  // A recorded result can be cited from then on, by any later answer.
  if (event.type === "tool.completed" && event.evidence) {
    const { recorded, cited } = state.citations;
    state = { ...state, citations: { recorded: [...recorded, event.evidence], cited } };
  }
  const id = `e:${envelope.session}:${envelope.seq}`;
  const isMain = envelope.parent === undefined;
  const run = envelope.run ?? "main";
  // A retry is shown while it is pending: the run's next event means it went ahead.
  const retry = event.type === "notice" && event.code === NOTICE.modelRetry;
  if (!retry) state = resumed(state, isMain, run);
  switch (event.type) {
    case "session.started":
      return { ...state, status: { ...state.status, model: event.model } };
    case "turn.started": {
      // A new question starts its own count; the last one's usage is not carried on.
      const { usage: _, ...status } = state.status;
      // A question the app wrote when it was sent is not written again. A think the last turn left open
      // (it stopped mid-think) is over.
      // A plan proposed is answered by this question, whatever it says.
      const { echoed, planReady: _ready, ...unthinking } = state;
      const { thinkingSince: _since, thinkingStartTs: _start, ...live } = unthinking.live;
      const rest = {
        ...unthinking,
        live: { ...live, thinking: false, reasoning: "" },
      };
      const written = echoed
        ? flushText(rest, id)
        : append(rest, id, { id, kind: "question", text: event.question });
      return {
        ...written,
        turn: {
          question: event.question,
          ...(event.mode === "plan" ? { plan: true as const } : {}),
          stepText: "",
          sinceResearch: "",
        },
        citations: { recorded: written.citations.recorded, cited: [] },
        status: { ...status, turnActive: true, since: Date.now() },
      };
    }
    case "model.reasoning.delta": {
      if (!isMain) return state;
      // A think that starts after text of its step: the text goes first, so the order is kept.
      if (!state.live.thinking && state.live.text.trim()) state = flushText(state, id, true);
      const started = state.live.thinkingStartTs ?? timeOf(envelope.ts);
      // The thinking stays live while it runs (its newest rows show); it goes to the scrollback when it ends.
      return {
        ...state,
        live: {
          ...state.live,
          thinking: true,
          thinkingSince: state.live.thinkingSince ?? Date.now(),
          ...(started !== undefined ? { thinkingStartTs: started } : {}),
          reasoning: state.live.reasoning + event.text.replaceAll("\r", ""),
        },
      };
    }
    case "model.text.delta": {
      if (!isMain) return state;
      const thought = closeThought(state, id, envelope.ts);
      // Line ends as \n only: a CR would hide a code fence from the cut.
      const text = state.live.text + event.text.replaceAll("\r", "");
      return commitStable(
        {
          ...thought,
          live: { ...thought.live, text },
          turn: { ...state.turn, stepText: state.turn.stepText + event.text },
          // What is written has been noted; the rest is noted again as it grows.
          citations: noteCited(thought.citations, text),
        },
        id,
      );
    }
    case "model.step.completed":
      return isMain
        ? {
            ...((closed) => ({
              ...closed,
              live: { ...closed.live, batch: { calls: [], mixed: false, held: new Map() } },
            }))(flushText(closeThought(release(state), id, envelope.ts), id)),
            turn: {
              ...state.turn,
              stepText: "",
              sinceResearch: [state.turn.sinceResearch, state.turn.stepText]
                .filter((t) => t.trim())
                .join("\n\n"),
            },
          }
        : state;
    case "tool.called": {
      // The main agent acting ends its thinking; its data calls join the step's batch. A research call
      // follows the step that made it: what that step and those before wrote is not the answer.
      if (isMain && researches(event.name)) state = { ...state, turn: { ...state.turn, sinceResearch: "" } };
      if (isMain && carriesOut(event)) state = { ...state, turn: { ...state.turn, worked: true } };
      if (isMain) {
        state = closeThought(state, id, envelope.ts);
        const batch = state.live.batch;
        if (batch && !BOOKKEEPING.has(event.name)) {
          const data = !MEMORY.has(event.name) && event.name !== AGENT_TOOL;
          state = {
            ...state,
            live: {
              ...state.live,
              batch: data ? { ...batch, calls: [...batch.calls, event.call] } : { ...batch, mixed: true },
            },
          };
        }
      }
      const tool: RunningTool = {
        run,
        call: event.call,
        name: event.name,
        nested: !isMain,
        ...(event.label ? { label: event.label } : {}),
        startedAt: Date.now(),
        ...since(envelope.ts),
      };
      // The title the main agent gives a sub-agent: what the agent's row shows.
      const title =
        isMain &&
        event.name === AGENT_TOOL &&
        typeof event.args === "object" &&
        event.args &&
        "title" in event.args
          ? (event.args as { title?: unknown }).title
          : undefined;
      if (typeof title === "string")
        state = { ...state, live: { ...state.live, titles: { ...state.live.titles, [event.call]: title } } };
      // A sub-agent's latest call is what its row says it is doing.
      const activity = [event.name, event.label].filter(Boolean).join(" ");
      const agents = isMain
        ? state.live.agents
        : state.live.agents.map((agent) => (agent.run === run ? { ...agent, activity } : agent));
      return { ...state, live: { ...state.live, tools: [...state.live.tools, tool], agents } };
    }
    case "tool.completed":
    case "tool.failed": {
      const owns = (tool: RunningTool) => tool.run === run && tool.call === event.call;
      const running = state.live.tools.find(owns);
      const remaining = state.live.tools.filter((tool) => !owns(tool));
      // A sub-agent's calls, done or failed, are counted on its line; its finished ones are not rows of
      // their own, nor are the main agent's calls to sub-agents (their rows say it) or its bookkeeping. Failures
      // are always shown.
      const ok = event.type === "tool.completed";
      // The main agent's call that started a sub-agent is that agent's row, however it ended and whichever
      // arrives first; one that never started an agent (refused) is a row of its own.
      if (isMain && state.live.delegated.includes(event.call)) {
        return { ...state, live: { ...state.live, tools: remaining } };
      }
      const calls = isMain
        ? state.live.calls
        : { ...state.live.calls, [run]: (state.live.calls[run] ?? 0) + 1 };
      const name = running?.name ?? "";
      if (ok && (!isMain || name === AGENT_TOOL || BOOKKEEPING.has(name))) {
        // A sub-agent's call that came back is kept for the full transcript.
        const what = [running?.name ?? message("app.someTool"), running?.label].filter(Boolean).join(" ");
        const results =
          !isMain && event.type === "tool.completed"
            ? {
                ...state.live.results,
                [run]: [...(state.live.results[run] ?? []), `${what}: ${event.summary}`],
              }
            : state.live.results;
        return { ...state, live: { ...state.live, tools: remaining, calls, results } };
      }
      // A sub-agent's failed call is listed under its row when it ends.
      if (!isMain && state.live.agents.some((agent) => agent.run === run) && event.type === "tool.failed") {
        const what = [running?.name ?? message("app.someTool"), running?.label].filter(Boolean).join(" ");
        const failures = {
          ...state.live.failures,
          [run]: [...(state.live.failures[run] ?? []), `${what}: ${event.error.message}`],
        };
        return { ...state, live: { ...state.live, tools: remaining, calls, failures } };
      }
      const owner = isMain ? undefined : state.live.agents.find((agent) => agent.run === run)?.label;
      const common = {
        id,
        kind: "tool" as const,
        name: running?.name ?? message("app.someTool"),
        nested: !isMain,
        ...(running?.label ? { label: running.label } : {}),
        ...(running ? { elapsedMs: took(running, envelope.ts) } : {}),
        ...(owner ? { agent: owner } : {}),
      };
      const block: ToolBlock =
        event.type === "tool.completed"
          ? {
              ...common,
              summary: event.summary,
              ...(event.source ? { source: event.source } : {}),
              // A sub-agent's calls show no preview: its row speaks for them.
              ...(event.preview && isMain ? { preview: event.preview } : {}),
            }
          : { ...common, summary: event.error.message, failed: true };
      // One of a step's data calls, three or more and nothing else beside them: held until all are in.
      const batch = isMain ? state.live.batch : undefined;
      // A call to a tool that does not exist fetched nothing: its step's calls stay rows of their own.
      const unknown = event.type === "tool.failed" && event.error.kind === "unknown_tool";
      if (
        batch &&
        !batch.mixed &&
        !unknown &&
        batch.calls.length >= GROUP_MIN &&
        batch.calls.includes(event.call)
      ) {
        const held = new Map(batch.held).set(event.call, block);
        const live = { ...state.live, calls, tools: remaining };
        if (batch.calls.some((call) => !held.has(call)))
          return { ...state, live: { ...live, batch: { ...batch, held } } };
        const members = batch.calls.map((call) => held.get(call) as ToolBlock);
        const group: BlockBody = {
          id,
          kind: "group",
          calls: members.map((member) => ({
            name: member.name,
            ...(member.label ? { label: member.label } : {}),
            ...(member.failed ? { failed: true, reason: member.summary } : { summary: member.summary }),
            ...(member.source ? { source: member.source } : {}),
            ...(member.elapsedMs !== undefined ? { elapsedMs: member.elapsedMs } : {}),
            ...(member.preview ? { preview: member.preview } : {}),
          })),
          ...(members.some((member) => member.elapsedMs !== undefined)
            ? { elapsedMs: Math.max(...members.map((member) => member.elapsedMs ?? 0)) }
            : {}),
        };
        return append(
          { ...state, live: { ...live, batch: { calls: [], mixed: true, held: new Map() } } },
          id,
          group,
        );
      }
      const next = append({ ...state, live: { ...state.live, calls } }, id, block);
      return { ...next, live: { ...next.live, tools: next.live.tools.filter((tool) => !owns(tool)) } };
    }
    case "agent.started":
      // The main agent names the model each turn runs on: a session's model can change between turns.
      if (isMain) return { ...state, status: { ...state.status, model: event.model } };
      return !envelope.run
        ? state
        : {
            ...state,
            live: {
              ...state.live,
              agents: [
                ...state.live.agents,
                {
                  run: envelope.run,
                  label: event.label ?? event.agent,
                  agent: event.agent,
                  ...(event.call && state.live.titles[event.call]
                    ? { title: state.live.titles[event.call] }
                    : {}),
                  startedAt: Date.now(),
                  ...since(envelope.ts),
                },
              ],
              delegated: event.call ? [...state.live.delegated, event.call] : state.live.delegated,
            },
          };
    case "agent.completed":
    case "agent.failed":
    case "agent.capped": {
      if (isMain) return state;
      const running = state.live.agents.find((agent) => agent.run === run && !agent.finished);
      if (!running) return state;
      const calls = state.live.calls[run];
      const failures = state.live.failures[run];
      const results = state.live.results[run];
      const member: AgentMember = {
        label: running.label,
        agent: running.agent,
        ...(running.title ? { title: running.title } : {}),
        summary: event.type === "agent.failed" ? "" : event.report?.trim() ? gist(event.report) : "",
        status:
          event.type === "agent.completed"
            ? "done"
            : event.type === "agent.capped"
              ? "capped"
              : event.error.kind === "cancelled"
                ? "stopped"
                : "failed",
        ...(event.type === "agent.failed" && event.error.kind !== "cancelled"
          ? { reason: event.error.message }
          : {}),
        ...(event.type === "agent.capped"
          ? { reason: message("app.stoppedAtLimit", { cap: event.cap }) }
          : {}),
        ...(calls ? { calls } : {}),
        elapsedMs: took(running, envelope.ts),
        ...(failures?.length ? { failures } : {}),
        ...(results?.length ? { tools: results } : {}),
      };
      const without = <T>(record: Record<string, T>) =>
        Object.fromEntries(Object.entries(record).filter(([key]) => key !== run));
      const agents = state.live.agents.map((agent) =>
        agent.run === run ? { ...agent, finished: member } : agent,
      );
      const ended = {
        ...state,
        live: {
          ...state.live,
          agents,
          tools: state.live.tools.filter((tool) => tool.run !== run),
          calls: without(state.live.calls),
          failures: without(state.live.failures),
          results: without(state.live.results),
        },
      };
      // The group is written once the last of it has ended.
      return agents.every((agent) => agent.finished) ? closeAgents(ended, id) : ended;
    }
    case "question.asked":
      // A turn that asks waits on the answer, not on approval of a plan it showed.
      return envelope.parent ? state : { ...state, turn: { ...state.turn, asked: true } };
    case "plan.updated":
      return isMain ? { ...state, live: { ...state.live, plan: event.steps } } : state;
    case "notice": {
      if (retry) {
        // A step asked for again is said while it is pending (the status row, or the agent's row), not kept:
        // if the retries run out, the run's failure says so. What it wrote so far stays where it was shown,
        // and is not the answer.
        const retrying: Retrying = event.retry ?? {};
        if (!isMain) {
          const agents = state.live.agents.map((agent) =>
            agent.run === run ? { ...agent, retrying } : agent,
          );
          return { ...state, live: { ...state.live, agents } };
        }
        const set = flushText(closeThought(state, id, envelope.ts), id);
        return { ...set, turn: { ...set.turn, stepText: "" }, live: { ...set.live, retrying } };
      }
      return append(state, id, {
        id,
        kind: "notice",
        level: event.level,
        text: event.text,
        ...(event.code === NOTICE.contextElided ? { context: true as const } : {}),
      });
    }
    case "compaction.started":
      return { ...state, live: { ...state.live, compacting: true } };
    case "compaction.completed":
    case "compaction.failed": {
      const { compacting: _, ...live } = state.live;
      const text =
        event.type === "compaction.completed"
          ? message("run.summarized", { turns: event.turns, kept: event.kept })
          : message("run.summaryFailed", { reason: event.error.message });
      const level = event.type === "compaction.completed" ? "info" : "warn";
      return append({ ...state, live }, id, { id, kind: "notice", level, text, context: true });
    }
    case "usage.updated":
      return { ...state, status: { ...state.status, usage: event.usage } };
    case "turn.completed": {
      // The answer is what was written since the last research call, the step under way included when a
      // turn ends without a closing step event; shown already when it was all streamed. A turn that asked
      // ends with its questions, which the question step shows: only what the model wrote is shown here.
      const written = [state.turn.sinceResearch, state.turn.stepText].filter((t) => t.trim()).join("\n\n");
      const streamed = event.answer.replace(/\s+/g, "") === written.replace(/\s+/g, "");
      const flushed = flushText(closeThought(state, id, envelope.ts), id);
      // The engine's numbering, for an answer not streamed and for the list of what it cited.
      const sources = event.sources ?? [];
      const answered = endTurn(
        flushed,
        id,
        envelope.ts,
        !streamed && !state.turn.asked && event.answer.trim() !== ""
          ? { id: `${id}:answer`, kind: "message", text: numberCitations(event.answer, sources) }
          : undefined,
      );
      const ended = sources.length
        ? push(answered, { id: `${id}:sources`, kind: "sources", sources })
        : answered;
      // The plan as it stood at the end: the steps done of all.
      // Skipped steps were decided against: they count neither way.
      const steps = state.live.plan.filter((step) => step.status !== "skipped");
      // A plan none of whose steps was marked done says nothing about how the turn went.
      const plan = steps.some((step) => step.status === "done")
        ? { plan: { done: steps.filter((step) => step.status === "done").length, total: steps.length } }
        : {};
      const { since: _, ...status } = ended.status;
      const proposed = state.turn.plan && !state.turn.asked && !state.turn.worked;
      return {
        ...(proposed ? { planReady: envelope.session } : {}),
        ...append(ended, `${id}:usage`, {
          id: `${id}:usage`,
          kind: "turnEnd",
          answered: {
            session: envelope.session,
            question: state.turn.question,
            ...(state.turn.plan ? { plan: true as const } : {}),
            answer: numberCitations(event.answer, sources),
            sources,
            ...(state.status.model ? { model: state.status.model } : {}),
            at: envelope.ts,
          },
          durationMs: event.durationMs,
          inputTokens: event.usage.inputTokens,
          outputTokens: event.usage.outputTokens,
          ...plan,
        }),
        status: { ...status, usage: event.usage },
      };
    }
    case "turn.cancelled":
      return endTurn(state, id, envelope.ts, {
        id: `${id}:end`,
        kind: "notice",
        level: "info",
        text: message("app.stopped"),
      });
    case "turn.failed":
      return endTurn(state, id, envelope.ts, {
        id: `${id}:end`,
        kind: "notice",
        level: "error",
        text: event.error.message,
      });
    default:
      return state;
  }
}

/** A report's first line, as plain text: what the transcript shows of a finished sub-agent. */
function gist(report: string): string {
  const line = report.split("\n").find((l) => l.trim()) ?? "";
  const plain = line.replace(/[#*_`>]/g, "").trim();
  return plain.length > 140 ? `${plain.slice(0, 139)}…` : plain || message("app.reportWritten");
}

/** What a running turn is doing, as the status row names it. */
type Phase = "stopping" | "summarizing" | "reconnecting" | "fetching" | "thinking" | "writing" | "working";

/**
 * The running turn's phase: stopping when a stop was asked; fetching while tools or sub-agents run; thinking
 * while the main agent reasons; writing once its step has streamed text (a part already committed still counts,
 * so the phase does not flicker as the answer is written); working otherwise.
 */
export function phaseOf(state: TranscriptState, stopping: boolean): Phase {
  if (stopping) return "stopping";
  // Sent, not started yet (or between a turn's end and the next): nothing of the next turn to name.
  if (!state.status.turnActive) return "working";
  if (state.live.compacting) return "summarizing";
  if (state.live.retrying) return "reconnecting";
  const fetching = (tool: RunningTool) =>
    !BOOKKEEPING.has(tool.name) && !MEMORY.has(tool.name) && tool.name !== AGENT_TOOL;
  if (state.live.agents.length || state.live.tools.some(fetching)) return "fetching";
  if (state.live.thinking) return "thinking";
  if (state.turn.stepText.trim()) return "writing";
  return "working";
}
