// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The engine: one session of questions and answers. It runs the main agent for each question and
 * turns everything the run emits into enveloped events, in order, with exactly one terminal event
 * per agent run and per turn. Clients read the events; callers that only need the result await
 * `outcome`.
 */

import { v7 } from "uuid";
import type { AgentFile } from "../agents/agent-file.js";
import { requestChars } from "../agents/budget.js";
import { type AgentOutcome, type AgentSpec, cacheKeyOf, runAgent } from "../agents/index.js";
import { ASKING, modeGuidance, NO_ONE_TO_ASK } from "../agents/prompts.js";
import {
  APP_NAME,
  addUsage,
  EVENT_SCHEMA_VERSION,
  type Event,
  type EventEnvelope,
  errorText,
  type Message,
  type Mode,
  type ModelClient,
  message,
  NOTICE,
  type Replay,
  type RouteName,
  type Sampling,
  type ToolSpec,
  type Usage,
} from "../contracts/index.js";
import { CALLS, CONTEXT, DEFAULT_LIMITS, type Limits, questionReserve } from "../contracts/limits.js";
import { citationsOf, type EvidenceRecord, EvidenceStore } from "../tools/evidence-store.js";
import { type Tool, ToolRegistry } from "../tools/index.js";
import { calendarContext } from "./calendar.js";
import { compact, compactionPlan, turnsOf } from "./compaction.js";
import { type RunRecord, type Skill, TurnRuntime } from "./delegation.js";
import type { Memory } from "./memory.js";

export type EngineOptions = {
  client: ModelClient;
  /** The model's route as a session remembers it. */
  route?: RouteName;
  /** Whether a call for data no source here serves brings the one-time sign-up nudge (true unless set). */
  signUpNudge?: boolean;
  registry: ToolRegistry;
  main: AgentSpec;
  /** The client's version, reported when the session starts. */
  version: string;
  session?: string;
  now?: () => Date;
  /** Sub-agents the main agent may call, and skills it may load (none unless given). */
  agents?: readonly AgentFile[];
  skills?: readonly Skill[];
  /** Where an earlier run of this session left off, when it is resumed. */
  restore?: RestoredState;
  /** Sampling for writing a summary of earlier turns (no thinking needed). */
  summarySampling?: Sampling;
  /** Notes, decisions and lessons kept across sessions; none unless given. */
  memory?: Memory;
  /** What a question and its agents may use; the defaults (step guards only) unless given. */
  limits?: Limits;
  /** Tools every agent has besides its data tools (compute, the evidence tool); none unless given. */
  core?: readonly Tool[];
  /** The session's recorded results; a store of this engine's own, kept in memory, unless given. */
  evidence?: EvidenceStore;
  /** Whether a person is there to answer the main agent's questions (the terminal UI); not unless set. */
  asks?: boolean;
};

/** What a resumed session continues from: its conversation and its counters. */
export type RestoredState = {
  history: Message[];
  /** The next envelope's sequence number, and the number of turns asked so far. */
  seq: number;
  turns: number;
  /** The history's size in tokens as the model last counted it, when known. */
  historyTokens?: number;
  /** Whether the session has already shown the sign-up nudge. */
  nudged?: boolean;
  /**
   * Whether the session has already started in this run, as when its engine is replaced between turns:
   * it is not said again to have started or resumed.
   */
  started?: boolean;
};

/**
 * How a turn changed the conversation the next turn starts from: the history that replaced the earlier
 * one when it was summarized, and the messages it added (none unless it finished).
 */
type HistoryChange = {
  replaced?: Message[];
  added: Message[];
  /** The size of the history after the turn, as the model counted it on the turn's last step. */
  tokens?: number;
};

/**
 * How a turn ended. `messages` is the main agent's conversation for the turn and `runs` its sub-agents'
 * (tool results included), for review; `usage` counts every run.
 */
export type TurnOutcome = Pick<AgentOutcome, "status" | "answer" | "usage" | "cap" | "error" | "messages"> & {
  runs: RunRecord[];
  history: HistoryChange;
  /** The results the turn's runs recorded, in order. */
  evidence: EvidenceRecord[];
  /** Time from the question to the end of its turn. */
  durationMs: number;
};

export type Turn = {
  /** The turn's id within its session ("t1", "t2", ...). */
  id: string;
  /** The turn's events; leaving the loop early cancels the turn. */
  events: AsyncIterable<EventEnvelope>;
  outcome: Promise<TurnOutcome>;
  cancel(): void;
};

/** `mode`: how the user wants the question worked (`auto` unless given). */
export type AskOptions = { signal?: AbortSignal; mode?: Mode };

export class Engine {
  readonly session: string;
  private seq = 0;
  private turns = 0;
  private started = false;
  /** The sign-up nudge shows at most once a session. */
  private nudged = false;
  private busy = false;
  private history: Message[] = [];
  /** The history's own size as the model last counted it (see historySize); unknown after it was cut or replaced. */
  private historyTokens: number | undefined;

  private readonly evidence: EvidenceStore;

  /** The names of the agents and skills this engine offers the main agent. */
  offered(): { agents: string[]; skills: string[] } {
    return {
      agents: (this.options.agents ?? []).map((spec) => spec.name),
      skills: (this.options.skills ?? []).map((skill) => skill.name),
    };
  }

  constructor(private readonly options: EngineOptions) {
    this.session = options.session ?? newSessionId();
    this.evidence = options.evidence ?? new EvidenceStore();
    const restore = options.restore;
    if (restore) {
      this.history = restore.history;
      this.historyTokens = restore.historyTokens;
      this.seq = restore.seq;
      this.turns = restore.turns;
      this.nudged = restore.nudged ?? false;
      this.started = restore.started ?? false;
    }
  }

  /** Where the session stands between turns, for an engine that takes over from this one. */
  state(): RestoredState {
    if (this.busy) throw new Error(message("run.busy"));
    return {
      history: this.history,
      seq: this.seq,
      turns: this.turns,
      ...(this.historyTokens !== undefined ? { historyTokens: this.historyTokens } : {}),
      nudged: this.nudged,
      started: this.started,
    };
  }

  /** The model the session's turns run on. */
  get model(): string {
    return this.options.client.model;
  }

  /** The model's route as a session remembers it, when known. */
  get route(): RouteName | undefined {
    return this.options.route;
  }

  /** Who the replay data this engine's model attaches may be sent back to, if anyone after the turn. */
  get replayKey(): string | undefined {
    return this.options.client.replayKey;
  }

  ask(question: string, { signal, mode = "auto" }: AskOptions = {}): Turn {
    if (this.busy) throw new Error(message("run.busy"));
    this.busy = true;
    const turn = `t${++this.turns}`;
    const run = `${turn}.main`;
    const controller = new AbortController();
    const abort = () => controller.abort();
    signal?.addEventListener("abort", abort, { once: true });
    if (signal?.aborted) abort();

    const queue = new EventQueue(abort);
    const { client, registry, main } = this.options;
    const envelope = (event: Event, run?: string, parent?: string): EventEnvelope => ({
      v: EVENT_SCHEMA_VERSION,
      seq: this.seq++,
      ts: (this.options.now?.() ?? new Date()).toISOString(),
      session: this.session,
      turn,
      ...(run ? { run } : {}),
      ...(parent ? { parent } : {}),
      event,
    });
    const emitTurn = (event: Event) => queue.push(envelope(event));
    const usage: Usage = { inputTokens: 0, outputTokens: 0 };
    // The question's limits run from here: its time (compaction and notes included) and the turn's tokens.
    const limits = this.options.limits ?? DEFAULT_LIMITS;
    const askedAt = Date.now();
    // The turn's length on a clock that a changed system time cannot move.
    const started = performance.now();
    const elapsed = () => Math.round(performance.now() - started);
    const questionEnds = limits.question.timeMs === undefined ? undefined : askedAt + limits.question.timeMs;
    // Adds one model call's usage to the turn's.
    const count = (step: Usage) => addUsage(usage, step);
    // Every run of the turn, the main agent's and its sub-agents', emits here; usage is the turn's total.
    const emitFor = (run: string, parent: string | undefined, event: Event) => {
      queue.push(envelope(event, run, parent));
      // The first call in the session for data no source here offers brings the sign-up nudge, once.
      if (
        event.type === "tool.failed" &&
        event.error.code === NOTICE.capabilityUnavailable &&
        this.options.signUpNudge !== false &&
        !this.nudged
      ) {
        this.nudged = true;
        queue.push(
          envelope({
            type: "notice",
            level: "info",
            code: NOTICE.capabilityUnavailable,
            text: message("data.signUp", { app: APP_NAME }),
          }),
        );
      }
      if (event.type === "model.step.completed") {
        count(event.usage);
        if (event.setAside) count(event.setAside);
        queue.push(envelope({ type: "usage.updated", usage: { ...usage } }));
      }
    };
    // The main agent's last step measures the conversation it was sent and what it wrote; that includes
    // the reasoning of every step of the turn, which the next turn does not carry.
    let lastStep: Usage | undefined;
    let reasoning = 0;
    const emitRun = (event: Event) => {
      if (event.type === "model.step.completed") {
        reasoning += event.usage.reasoningTokens ?? 0;
        if (event.usage.inputTokens) lastStep = event.usage;
      }
      emitFor(run, undefined, event);
    };
    // What the main agent's requests send besides the conversation: its system prompt and tool specs.
    let overhead: { system: string; tools: ToolSpec[] } | undefined;
    // A model call made for the turn outside its runs (a summary, a lesson) reports its usage as
    // usage.updated: it counts toward the turn, not as a step of the main agent.
    const emitAside = (event: Event) => {
      if (event.type === "usage.updated") {
        count(event.usage);
        emitTurn({ type: "usage.updated", usage: { ...usage } });
      } else emitRun(event);
    };

    if (!this.started) {
      this.started = true;
      emitTurn({
        type: "session.started",
        model: client.model,
        version: this.options.version,
      });
      if (this.options.restore) emitTurn({ type: "session.resumed", fromSeq: this.options.restore.seq });
    }
    emitTurn({ type: "turn.started", question, mode });
    emitRun({ type: "agent.started", agent: main.name, tier: "deep", model: client.model });

    // The main agent reads the turn's dates from its context rather than working out weekdays itself.
    const calendar = calendarContext(this.options.now?.() ?? new Date());
    const runtime = new TurnRuntime({
      session: this.session,
      turn,
      main: run,
      client,
      data: registry.list(),
      core: this.options.core ?? [],
      evidence: this.evidence,
      agents: this.options.agents ?? [],
      skills: this.options.skills ?? [],
      calendar,
      emit: emitFor,
      limits,
      spentTokens: () => usage.inputTokens + usage.outputTokens,
      clock: this.options.now ?? (() => new Date()),
      ...(this.options.asks ? { asks: true } : {}),
      ...(questionEnds !== undefined ? { questionEnds } : {}),
      model: {
        ...(main.contextWindow ? { contextWindow: main.contextWindow } : {}),
        ...(main.inputLimit ? { inputLimit: main.inputLimit } : {}),
        ...(main.sampling ? { sampling: main.sampling } : {}),
        ...(main.hurriedSampling ? { hurriedSampling: main.hurriedSampling } : {}),
      },
    });
    const memory = this.options.memory?.turnTools({
      session: this.session,
      turn,
      emit: emitAside,
    });
    const tools = [...runtime.tools(), ...(memory?.tools ?? [])];
    const data = new Set(registry.list().map((tool) => tool.name));
    // The main agent's context: its prompt, the skills it may load, the user's saved notes and the turn's dates.
    const specWith = (notes: string) => ({
      ...main,
      system: [
        main.system,
        this.options.asks ? ASKING : NO_ONE_TO_ASK,
        runtime.agentList(),
        runtime.skillList(),
        notes,
        calendar,
        modeGuidance(mode),
      ]
        .filter(Boolean)
        .join("\n\n"),
      tools: [...main.tools, ...tools.map((tool) => tool.name).filter((name) => !data.has(name))],
    });
    let before = this.history.length;
    // A summary replaces the history only if the turn that needed it finishes.
    const earlier = this.history;
    let replaced: Message[] | undefined;
    // Preparing the question (compaction, notes) ends with gathering, leaving the answer its reserve.
    const preparing =
      questionEnds === undefined
        ? controller.signal
        : AbortSignal.any([
            controller.signal,
            AbortSignal.timeout(Math.max(0, questionEnds - questionReserve(limits) - Date.now())),
          ]);
    const outcome = this.compactIfNeeded(question, preparing, controller.signal, emitTurn, emitAside)
      .then(async (compacted) => {
        let asked = question;
        if (compacted) {
          replaced = compacted.history;
          this.history = compacted.history;
          before = compacted.history.length;
          // With no turn kept, the summary opens this turn's question.
          if (compacted.prefix) asked = `${compacted.prefix}\n\n---\n\n${question}`;
        }
        // The user's notes, read within the question's time; without them when it runs out first.
        const notes = await untilAborted(
          this.options.memory?.notesContext().catch(() => "") ?? Promise.resolve(""),
          preparing,
          "",
        );
        const mainCaps = {
          steps: limits.question.steps,
          ...(limits.question.tokens !== undefined ? { turnTokens: limits.question.tokens } : {}),
          ...(questionEnds !== undefined
            ? {
                timeMs: Math.max(0, Math.floor(questionEnds - Date.now())),
                reserveMs: questionReserve(limits),
              }
            : {}),
        };
        const mainSpec = { ...specWith(notes), caps: mainCaps };
        const mainTools = new ToolRegistry(tools);
        overhead = { system: mainSpec.system, tools: mainTools.specs(mainSpec.tools) };
        return runAgent(
          mainSpec,
          asked,
          {
            client,
            registry: mainTools,
            emit: emitRun,
            signal: controller.signal,
            spentTokens: () => usage.inputTokens + usage.outputTokens,
            evidence: (step, signal) => this.evidence.scope(turn, run, step, signal),
            clock: this.options.now ?? (() => new Date()),
            cacheKey: cacheKeyOf(this.session),
          },
          this.history,
        );
      })
      .catch(
        (error: unknown): AgentOutcome => ({
          status: "failed",
          answer: "",
          usage,
          messages: [],
          error: { kind: "internal", message: errorText(error) },
        }),
      )
      .then(async (result) => {
        // Every sub-agent ends, with its own terminal event, before the turn does; by the question's
        // time limit when it has one.
        const toWall =
          questionEnds === undefined ? undefined : Math.max(0, Math.floor(questionEnds - Date.now()));
        const runs = await runtime.close(
          toWall === undefined ? undefined : Math.min(toWall, CALLS.subagentsStopMs),
        );
        // Nothing still running records into a turn whose outcome is being written.
        this.evidence.closeTurn(turn);
        // A decision the main agent recorded is kept only with an answer (and, with a time limit, within it).
        if (memory && (result.status === "completed" || result.status === "capped")) {
          const left =
            questionEnds === undefined ? undefined : Math.max(0, Math.floor(questionEnds - Date.now()));
          await memory
            .commit(left === undefined ? undefined : AbortSignal.timeout(left))
            .catch((error: unknown) =>
              emitRun({
                type: "notice",
                level: "warn",
                code: NOTICE.memoryFailed,
                text: message("run.decisionNotSaved", {
                  reason: errorText(error),
                }),
              }),
            );
        }
        // The answer's citations, numbered for people; ids that name no record are kept apart.
        const cited = (answer: string) => {
          const { sources, missing } = citationsOf(answer, (id) => this.evidence.get(id));
          return {
            ...(sources.length ? { sources } : {}),
            ...(missing.length ? { missingCitations: missing } : {}),
          };
        };
        switch (result.status) {
          case "completed":
            emitRun({ type: "agent.completed", report: result.answer });
            emitTurn({
              type: "turn.completed",
              answer: result.answer,
              ...cited(result.answer),
              usage: { ...usage },
              durationMs: elapsed(),
            });
            break;
          case "capped":
            emitRun({ type: "agent.capped", cap: result.cap ?? "steps" });
            emitTurn({
              type: "turn.completed",
              answer: result.answer,
              ...cited(result.answer),
              usage: { ...usage },
              durationMs: elapsed(),
            });
            break;
          case "cancelled":
            emitRun({
              type: "agent.failed",
              error: { kind: "cancelled", message: message("run.cancelled") },
            });
            emitTurn({ type: "turn.cancelled" });
            break;
          case "failed":
            emitRun({
              type: "agent.failed",
              error: result.error ?? { kind: "internal" as const, message: "failed" },
            });
            emitTurn({
              type: "turn.failed",
              error: result.error ?? { kind: "internal" as const, message: "failed" },
            });
            break;
        }
        // A finished turn is part of the conversation; a cancelled or failed one is not carried on.
        const finished = result.status === "completed" || result.status === "capped";
        // Reasoning counts only while the next turn does not carry it.
        const measured =
          lastStep && overhead
            ? historySize(
                lastStep,
                this.options.client.keepsReasoning === "conversation" ? 0 : reasoning,
                overhead.system,
                overhead.tools,
              )
            : undefined;
        if (finished) {
          const kept = this.history;
          this.history = settled(result.messages, this.options.client);
          this.historyTokens = measured;
          // The turn changed what came before it (a result set aside to fit): all of it is written again.
          // After a summary too: what was written for it is replaced by what the turn made of it.
          if (result.messages.slice(0, before).some((message, index) => message !== kept[index])) {
            replaced = this.history.slice(0, before);
          }
        } else if (replaced) {
          this.history = earlier;
          replaced = undefined;
        }
        const history = {
          ...(replaced ? { replaced } : {}),
          added: finished ? this.history.slice(before) : [],
          ...(finished && measured ? { tokens: measured } : {}),
        };
        signal?.removeEventListener("abort", abort);
        this.busy = false;
        queue.close();
        const { status, answer } = result;
        return {
          status,
          answer,
          durationMs: elapsed(),
          usage: { ...usage },
          messages: result.messages,
          runs,
          history,
          evidence: this.evidence.of(turn),
          ...(result.cap ? { cap: result.cap } : {}),
          ...(result.error ? { error: result.error } : {}),
        };
      });

    return { id: turn, events: queue, outcome, cancel: abort };
  }

  /**
   * The history summarized when it and the question would take more than half the context window;
   * undefined when nothing was summarized. A summary that fails leaves the history as it was, and
   * the loop sets old results aside as it needs to. `signal` ends the summary (the turn cancelled, or
   * its time for preparing over) and `cancelled` says which. `emit` reports it for the turn; the summary's
   * usage goes to `count`.
   */
  private async compactIfNeeded(
    question: string,
    signal: AbortSignal,
    cancelled: AbortSignal,
    emit: (event: Event) => void,
    count: (event: Event) => void,
  ): Promise<{ history: Message[]; prefix?: string } | undefined> {
    const window = this.options.main.contextWindow;
    if (window === undefined) return undefined;
    const plan = compactionPlan(this.history, question, window, this.historyTokens);
    if (!plan) return undefined;
    const turns = turnsOf(plan.summarize).length;
    emit({ type: "compaction.started", turns });
    const result = await compact(plan, window, this.options.client, this.options.summarySampling, signal);
    count({ type: "usage.updated", usage: result.usage });
    // A cancelled turn says so itself.
    if (cancelled.aborted) return undefined;
    if ("error" in result) {
      emit({ type: "compaction.failed", error: result.error });
      return undefined;
    }
    emit({
      type: "compaction.completed",
      turns,
      kept: turnsOf(plan.keep).length,
      ...(this.historyTokens !== undefined ? { tokensBefore: this.historyTokens } : {}),
    });
    return { history: result.history, ...(result.prefix ? { prefix: result.prefix } : {}) };
  }
}

/** A new session's id: a UUID v7, which sorts by when the session started. */
export function newSessionId(): string {
  return v7();
}

/** The shape of a session id: a UUID v7, lowercase, as newSessionId makes it. */
export const SESSION_ID = /^[0-9a-f]{8}-[0-9a-f]{4}-7[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;

/** Events from the run to one reader, in order. Leaving the reading loop early cancels the turn. */
export class EventQueue implements AsyncIterable<EventEnvelope> {
  private readonly items: EventEnvelope[] = [];
  private closed = false;
  private detached = false;
  private wake: (() => void) | undefined;

  constructor(private readonly onDetach: () => void) {}

  push(item: EventEnvelope): void {
    if (this.closed || this.detached) return;
    this.items.push(item);
    this.wake?.();
  }

  close(): void {
    this.closed = true;
    this.wake?.();
  }

  [Symbol.asyncIterator](): AsyncIterator<EventEnvelope> {
    return {
      next: async () => {
        while (!this.items.length && !this.closed && !this.detached) {
          await new Promise<void>((resolve) => {
            this.wake = resolve;
          });
        }
        const item = this.items.shift();
        return item ? { done: false, value: item } : { done: true, value: undefined };
      },
      return: async () => {
        if (!this.closed) this.onDetach();
        this.detached = true;
        this.items.length = 0;
        this.wake?.();
        return { done: true, value: undefined };
      },
    };
  }
}

/**
 * A finished turn as the next one sees it: what was said and done, without the reasoning, and without
 * what a provider attached that carries it (its `settleReplay` says). Most providers need reasoning back
 * only within the turn that produced it, and thinking models' cards ask for multi-turn history to hold
 * only the final output; a provider that requires earlier turns' reasoning keeps it.
 */
export function settled(
  messages: Message[],
  { keepsReasoning, settleReplay }: Pick<ModelClient, "keepsReasoning" | "settleReplay"> = {},
): Message[] {
  if (keepsReasoning === "conversation") return messages;
  const settle = <T extends { replay?: Replay }>(item: T): T => {
    if (!item.replay || !settleReplay) return item;
    const { replay, ...rest } = item;
    const kept = settleReplay(replay);
    return (kept ? { ...rest, replay: kept } : rest) as T;
  };
  return messages.flatMap((message): Message[] => {
    if (message.role !== "assistant") return [message];
    const parts = message.parts.filter((part) => part.type !== "reasoning").map(settle);
    return parts.length ? [{ ...message, parts }] : [];
  });
}

/**
 * The conversation's own size from the main agent's last step: what it was sent and wrote, less the
 * `reasoning` of the turn's steps, which that includes and the next turn does not carry, and less the
 * system prompt and tool specs, which compaction cannot reduce. The overhead counts at prose's rate,
 * so it is never overstated.
 */
function historySize(step: Usage, reasoning: number, system: string, tools: readonly ToolSpec[]): number {
  const overhead = Math.floor(requestChars(system, [], tools) / CONTEXT.savedCharsPerToken);
  return Math.max(0, step.inputTokens + step.outputTokens - reasoning - overhead);
}

/** `work`'s result, or `instead` once `signal` is aborted first. */
function untilAborted<T>(work: Promise<T>, signal: AbortSignal, instead: T): Promise<T> {
  if (signal.aborted) return Promise.resolve(instead);
  let stop = () => {};
  const aborted = new Promise<T>((resolve) => {
    stop = () => resolve(instead);
    signal.addEventListener("abort", stop, { once: true });
  });
  return Promise.race([work, aborted]).finally(() => signal.removeEventListener("abort", stop));
}
