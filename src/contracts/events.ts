// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The event protocol between the engine and every client (terminal UI, headless JSON, tests).
 *
 * Events are plain JSON. `v` changes only on a breaking change; clients ignore event types and
 * fields they do not know, so additive changes keep the version.
 */
import { z } from "zod";
import { sourceSchema } from "./citations.js";

export const EVENT_SCHEMA_VERSION = 1 as const;

/** The main agent's tool that asks the person questions; its run ends with them (question.asked). */
export const ASK_TOOL = "ask_user";

/** What a tool is: data reads a source, compute derives, agent is an agent's report, control keeps the books. */
const TOOL_KINDS = ["data", "compute", "agent", "control"] as const;
export type ToolKind = (typeof TOOL_KINDS)[number];

/**
 * Whether a call carries the research out (computes, or hands work to an agent), as against looking
 * something up or keeping the books. A plan-mode turn that made none proposed a plan: it can be run as it
 * stands.
 */
export function carriesOut(call: { kind?: ToolKind | undefined }): boolean {
  return call.kind === "compute" || call.kind === "agent";
}

/** What a notice is about, for a program to act on; a cap's notice is `cap_<cap>`. */
export const NOTICE = {
  answerCut: "answer_cut",
  answerEmpty: "answer_empty",
  capabilityUnavailable: "capability_unavailable",
  contextElided: "context_elided",
  memoryFailed: "memory_failed",
  modelRetry: "model_retry",
} as const;

const CAPS = ["steps", "subagents", "tokens", "time"] as const;

/**
 * A result's preview for people: a few rows of cells (text, no width), the columns to set right (numbers),
 * how many rows more there are, and whether it says all the call's summary does (then the summary is left
 * out of the call's row).
 */
const previewSchema = z.object({
  rows: z.array(z.array(z.string())).min(1),
  right: z.array(z.number().int().nonnegative()).optional(),
  more: z.number().int().positive().optional(),
  replacesSummary: z.literal(true).optional(),
});
export type Preview = z.infer<typeof previewSchema>;

/**
 * How the user wants a question worked: `auto`, the main agent decides how deep to go and whom to ask;
 * `plan`, it proposes a research plan first and carries it out once the user approves or edits it.
 */
export const MODES = ["auto", "plan"] as const;
export type Mode = (typeof MODES)[number];

/** How a data source failed, by how its caller reacts. */
const DATA_ERROR_KINDS = [
  "not_configured",
  "rejected",
  "quota",
  "rate_limited",
  "unavailable",
  "unsupported",
  "no_data",
  "invalid",
  "conflict",
  "diverged",
  "full",
] as const;

/** How a model request failed. */
export const MODEL_ERROR_KINDS = ["aborted", "auth", "rate_limited", "context", "provider"] as const;

/**
 * Every kind a run, an agent or a tool call fails with: the model's, the run's own, and a tool call's
 * (a data source's failure as `data_<kind>`).
 */
const ERROR_KINDS = [
  ...MODEL_ERROR_KINDS,
  "internal",
  "cancelled",
  "failed",
  "no_report",
  "content_filter",
  "unknown_tool",
  "invalid_arguments",
  "refused",
  ...DATA_ERROR_KINDS.map((kind) => `data_${kind}` as const),
] as const;

const id = z.string().min(1);
const usage = z.object({
  inputTokens: z.number().int().nonnegative(),
  outputTokens: z.number().int().nonnegative(),
  reasoningTokens: z.number().int().nonnegative().optional(),
  /** Input tokens read from the provider's prompt cache, part of `inputTokens`. */
  cacheReadTokens: z.number().int().nonnegative().optional(),
  /** Input tokens written to the provider's prompt cache, part of `inputTokens`. */
  cacheWriteTokens: z.number().int().nonnegative().optional(),
});
const errorInfo = z.object({
  kind: z.enum(ERROR_KINDS),
  message: z.string(),
  hint: z.string().optional(),
  /** A finer reason a program can act on (a data source's `capability_unavailable`, say). */
  code: z.string().optional(),
});
const cap = z.enum(CAPS);
const noticeCode = z.enum([...Object.values(NOTICE), ...CAPS.map((name) => `cap_${name}` as const)]);

const eventSchemas = [
  // session
  z.object({
    type: z.literal("session.started"),
    model: z.string(),
    version: z.string(),
  }),
  z.object({ type: z.literal("session.resumed"), fromSeq: z.number().int().nonnegative() }),
  // turn: one user question
  z.object({
    type: z.literal("turn.started"),
    question: z.string(),
    /** The mode the question was asked in. */
    mode: z.enum(MODES),
  }),
  z.object({
    type: z.literal("turn.completed"),
    /** As the model wrote it, citing recorded results by id ([e7]); numberCitations writes it for people. */
    answer: z.string(),
    /** The recorded results the answer cites, numbered by first appearance. */
    sources: z.array(sourceSchema).optional(),
    /** Ids the answer cites that name no recorded result; left out of the numbered text. */
    missingCitations: z.array(z.string()).optional(),
    usage,
    /** Time from the question to its answer. */
    durationMs: z.number().nonnegative(),
  }),
  z.object({ type: z.literal("turn.cancelled") }),
  z.object({ type: z.literal("turn.failed"), error: errorInfo }),
  // agent runs: the main agent and its sub-agents
  z.object({
    type: z.literal("agent.started"),
    agent: z.string(),
    /** What people see the agent called ("Equity Research"); the agent's name when absent. */
    label: z.string().optional(),
    tier: z.enum(["deep", "quick"]),
    model: z.string(),
    /** The main agent's call that started it (its run_agent call), so the call's row is the agent's. */
    call: z.string().optional(),
  }),
  z.object({ type: z.literal("agent.completed"), report: z.string() }),
  z.object({ type: z.literal("agent.failed"), error: errorInfo }),
  // A capped run may still have written a report from what it had.
  z.object({ type: z.literal("agent.capped"), cap, report: z.string().optional() }),
  // model stream
  z.object({ type: z.literal("model.text.delta"), text: z.string() }),
  z.object({ type: z.literal("model.reasoning.delta"), text: z.string() }),
  // setAside: what attempts set aside before the step's own used (a blank reply asked for again): it
  // counts toward the turn, but only `usage` measures the step's request.
  z.object({
    type: z.literal("model.step.completed"),
    finish: z.string(),
    usage,
    setAside: usage.optional(),
  }),
  // tools
  z.object({
    type: z.literal("tool.called"),
    call: id,
    name: z.string(),
    args: z.json(),
    /** The call's arguments in a few words for people ("NVDA income statement, quarterly"). */
    label: z.string(),
    /** What the tool is, when it is registered. */
    kind: z.enum(TOOL_KINDS).optional(),
  }),
  z.object({
    type: z.literal("tool.completed"),
    call: id,
    summary: z.string(),
    chars: z.number().int().nonnegative(),
    source: z.string().optional(),
    /** The id the result was recorded under (`e7`), for a result that was. */
    evidence: z.string().optional(),
    /** The last date the result's data describes, when it says. */
    asOf: z.string().optional(),
    /** What the result holds, a few rows of it for people, when it has any. */
    preview: previewSchema.optional(),
  }),
  z.object({ type: z.literal("tool.failed"), call: id, error: errorInfo }),
  // compaction: earlier turns summarized before the question, ended by exactly one of completed or failed
  // (a cancelled turn ends it with turn.cancelled)
  z.object({ type: z.literal("compaction.started"), turns: z.number().int().positive() }),
  z.object({
    type: z.literal("compaction.completed"),
    /** The turns summarized, and those kept as they were (the latest, when it fits). */
    turns: z.number().int().positive(),
    kept: z.number().int().nonnegative(),
    /** The history's size before, as the model last counted it, when known. */
    tokensBefore: z.number().int().nonnegative().optional(),
  }),
  /** The history is left as it was; the loop sets old results aside as it needs to. */
  z.object({ type: z.literal("compaction.failed"), error: errorInfo }),
  // questions the main agent asked the user: its run ends with them, and the reply is the next question
  z.object({
    type: z.literal("question.asked"),
    questions: z.array(
      z.object({
        header: z.string(),
        question: z.string(),
        options: z.array(z.object({ label: z.string(), note: z.string().optional() })),
      }),
    ),
  }),
  // plan: shown to the user, never awaited
  z.object({
    type: z.literal("plan.updated"),
    steps: z.array(z.object({ text: z.string(), status: z.enum(["pending", "active", "done", "skipped"]) })),
  }),
  // memory
  z.object({ type: z.literal("memory.recalled"), entries: z.number().int().nonnegative() }),
  z.object({ type: z.literal("memory.written"), kind: z.enum(["note", "decision", "lesson"]) }),
  // user-facing notices and running totals
  z.object({
    type: z.literal("notice"),
    level: z.enum(["info", "warn", "error"]),
    code: noticeCode,
    text: z.string(),
    /** A model step asked for again (`model_retry`): which retry this is, of how many it may take. */
    retry: z.object({ attempt: z.number().int().positive(), of: z.number().int().positive() }).optional(),
  }),
  z.object({ type: z.literal("usage.updated"), usage }),
] as const;

const eventSchema = z.discriminatedUnion("type", eventSchemas);

const envelopeFields = {
  v: z.literal(EVENT_SCHEMA_VERSION),
  seq: z.number().int().nonnegative(),
  ts: z.iso.datetime(),
  session: id,
  turn: id.optional(),
  /** The agent run the event belongs to (`t1.main`, `t1.equity.1`). */
  run: id.optional(),
  parent: id.optional(),
};
const envelopeSchema = z.object({ ...envelopeFields, event: eventSchema });
// The envelope with any event, so a newer engine's unknown event types can be skipped rather than rejected.
const looseEnvelopeSchema = z.object({ ...envelopeFields, event: z.looseObject({ type: z.string() }) });

export type Event = z.infer<typeof eventSchema>;
type EventType = Event["type"];
export type EventEnvelope = z.infer<typeof envelopeSchema>;
export type Usage = z.infer<typeof usage>;
export type Cap = z.infer<typeof cap>;
export type ErrorInfo = z.infer<typeof errorInfo>;
export type ErrorKind = ErrorInfo["kind"];
export type DataErrorKind = (typeof DATA_ERROR_KINDS)[number];
export type Question = Extract<Event, { type: "question.asked" }>["questions"][number];

const BREAKDOWNS = ["reasoningTokens", "cacheReadTokens", "cacheWriteTokens"] as const;

/** Adds one model call's usage to a total; a breakdown appears once a call reports it. */
export function addUsage(total: Usage, step: Usage | undefined): void {
  if (!step) return;
  total.inputTokens += step.inputTokens;
  total.outputTokens += step.outputTokens;
  for (const key of BREAKDOWNS) {
    const value = step[key];
    if (value !== undefined) total[key] = (total[key] ?? 0) + value;
  }
}

type ParseResult<T> = { ok: true; value: T } | { ok: false; error: string };

/**
 * Validate one envelope read from a session file, a child process or the network.
 * An envelope whose event type this version does not know is valid and returns `null`: skip it.
 */
export function parseEnvelope(input: unknown): ParseResult<EventEnvelope | null> {
  const loose = looseEnvelopeSchema.safeParse(input);
  if (!loose.success) return { ok: false, error: z.prettifyError(loose.error) };
  if (!isKnownEventType(loose.data.event.type)) return { ok: true, value: null };
  const parsed = envelopeSchema.safeParse(input);
  return parsed.success
    ? { ok: true, value: parsed.data }
    : { ok: false, error: z.prettifyError(parsed.error) };
}

/** Whether a client knows this event type. Unknown types are skipped, not rejected. */
function isKnownEventType(type: unknown): type is EventType {
  return typeof type === "string" && eventSchemas.some((schema) => schema.shape.type.value === type);
}

/**
 * The JSON Schema of the envelope, which the tests hold to the parser. Like `parseEnvelope`, it accepts
 * fields it does not name and event types it does not know.
 */
export function eventJsonSchema(): object {
  const known = eventSchemas.map((schema) => schema.shape.type.value);
  const unknownEvent = {
    type: "object",
    properties: { type: { type: "string", not: { enum: known } } },
    required: ["type"],
  };
  const envelope = z.toJSONSchema(z.object({ ...envelopeFields, event: eventSchema }), {
    target: "draft-2020-12",
    io: "input",
  }) as unknown as { properties: { event: object } };
  envelope.properties.event = { anyOf: [envelope.properties.event, unknownEvent] };
  return envelope;
}
