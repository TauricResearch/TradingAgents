// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The tools an agent may call, and how one call runs: arguments checked against the tool's schema,
 * failures turned into text the model can act on, and output kept within a budget.
 */

import { z } from "zod";
import type { JsonValue, Preview, ToolCall, ToolSpec } from "../contracts/index.js";
import { errorText, message, printable } from "../contracts/index.js";
import { CALLS, EVIDENCE } from "../contracts/limits.js";
import { DataError } from "../data/errors.js";
import { dateText, previewOf } from "./preview.js";
import { holdsReference, resolveReferences } from "./references.js";
import { renderResult } from "./render.js";
import { inputSchema, type Tool, type ToolAnswer, type ToolContext, ToolRefusalError } from "./tool.js";
import { shortened, sourceOf } from "./tool-text.js";

/** Why a call failed, for the transcript; the model reads `output`. */
type CallFailure =
  | "unknown_tool"
  | "invalid_arguments"
  | "cancelled"
  | "failed"
  | "refused"
  | `data_${DataError["kind"]}`;

type CallOutcome = {
  /** What the model reads back. */
  output: string;
  /** A one-line account for the transcript. */
  summary: string;
  source?: string;
  /** The full length before any cut. */
  chars: number;
  /** Whether the output was cut to the budget. */
  truncated: boolean;
  failure?: CallFailure;
  /** A data failure's own code, when it has one. */
  code?: string;
  /** The recorded result the output shows (`e7`). */
  evidence?: string;
  /** The run's closing message, when the call ends the run (see ToolReply). */
  ends?: string;
  /** The last date the result's data describes, when its provenance says. */
  asOf?: string;
  /** A few rows of what came back, for people (preview.ts). */
  preview?: Preview;
};

export class ToolRegistry {
  private readonly tools = new Map<string, Tool>();

  constructor(tools: Tool[] = []) {
    for (const tool of tools) this.add(tool);
  }

  add(tool: Tool): void {
    if (this.tools.has(tool.name)) throw new Error(`tool ${tool.name} is registered twice`);
    // Tool arguments are a JSON object; refuse anything else here rather than at the first call.
    const schema = inputSchema(tool);
    if (schema.type !== "object") throw new Error(`tool ${tool.name} must take an object of arguments`);
    this.tools.set(tool.name, tool);
  }

  /** Every tool registered. */
  list(): Tool[] {
    return [...this.tools.values()];
  }

  /** What the named tool is (data, compute, agent or control), if it is registered. */
  kindOf(name: string): Tool["kind"] | undefined {
    return this.tools.get(name)?.kind;
  }

  /** The specs of the named tools, for a model request. */
  specs(names: readonly string[]): ToolSpec[] {
    return names.map((name) => {
      const tool = this.tools.get(name);
      if (!tool) throw new Error(`unknown tool ${name}`);
      return {
        name: tool.name,
        description: tool.description,
        inputSchema: inputSchema(tool) as { [key: string]: JsonValue },
      };
    });
  }

  /**
   * A call's arguments in a few words for people, at most `LABEL_CHARS` long: the tool's own label when
   * it has one, else the values the model gave for what the tool takes, paging left out. References are
   * read from `evidence` first, so a label names the results they point to (NVDA), never their ids. Nothing
   * for an unknown tool or arguments that do not fit it (a value it does not take is never shown). Never throws.
   */
  label(name: string, args: JsonValue, evidence?: ToolContext["evidence"], now: Date = new Date()): string {
    const tool = this.tools.get(name);
    if (!tool) return "";
    let read: unknown = args;
    if (tool.kind === "compute" && evidence && holdsReference(args)) {
      const resolved = resolveReferences(args, evidence, evidence);
      if (resolved.ok) read = resolved.value;
    }
    const parsed = tool.input.safeParse(read);
    return parsed.success ? labelText(tool, read, parsed.data, undefined, now) : "";
  }

  /** Whether every call can run at the same time as others. */
  parallelSafe(calls: readonly ToolCall[]): boolean {
    return calls.every((call) => this.tools.get(call.name)?.parallelSafe === true);
  }

  /**
   * Run one call of a tool from `allowed` (the tools the model was offered). Never throws: every
   * failure becomes an outcome the model can read. A cancelled call returns at once, even if the
   * tool itself has not stopped yet.
   */
  async execute(
    call: ToolCall,
    allowed: ReadonlySet<string>,
    context: ToolContext,
    budget: number = CALLS.resultChars,
  ): Promise<CallOutcome> {
    const fail = (text: string, failure: CallFailure, source?: string, code?: string) =>
      failed(text, failure, source, budget, code);
    const tool = allowed.has(call.name) ? this.tools.get(call.name) : undefined;
    if (!tool) {
      return fail(
        `There is no tool named ${call.name}. Use one of: ${[...allowed].join(", ")}.`,
        "unknown_tool",
      );
    }
    let args: unknown = call.args;
    let inputs: string[] = [];
    if (tool.kind === "compute" && holdsReference(args)) {
      const resolved = context.evidence
        ? resolveReferences(args, context.evidence, context.evidence)
        : { ok: false as const, error: "references to earlier results are not available here" };
      if (!resolved.ok) {
        return fail(`The arguments do not fit ${call.name}: ${resolved.error}`, "invalid_arguments");
      }
      args = resolved.value;
      inputs = resolved.inputs;
    }
    const parsed = tool.input.safeParse(args);
    if (!parsed.success) {
      return fail(
        `The arguments do not fit ${call.name}: ${z.prettifyError(parsed.error)}`,
        "invalid_arguments",
      );
    }
    // A call whose run was cancelled before it started is answered without running.
    if (context.signal.aborted) return fail(message("call.cancelled"), "cancelled");
    let stop = () => {};
    const cancelled = new Promise<"cancelled">((resolve) => {
      stop = () => resolve("cancelled");
      if (context.signal.aborted) stop();
      context.signal.addEventListener("abort", stop, { once: true });
    });
    try {
      const answer = await Promise.race([
        tool.run(parsed.data, { ...context, call: call.callId }),
        cancelled,
      ]);
      if (answer === "cancelled") return fail(message("call.cancelled"), "cancelled");
      // A control tool's reply is read as the tool words it: no record, no head, no provenance.
      if ("text" in answer) {
        if (tool.kind !== "control") {
          return fail(
            message("call.failed", {
              tool: call.name,
              reason: "its reply in words did not fit its contract: only a control tool replies in words",
            }),
            "failed",
          );
        }
        return {
          ...bounded(answer.text, budget),
          summary: summarize(answer.summary ?? answer.text),
          ...(answer.ends ? { ends: answer.ends } : {}),
        };
      }
      return this.recorded(call, tool, answer, { args, input: parsed.data, inputs }, context, budget);
    } catch (error) {
      if (context.signal.aborted) return fail(message("call.cancelled"), "cancelled");
      if (error instanceof ToolRefusalError) return fail(error.message, "refused");
      if (error instanceof DataError) {
        return fail(dataFailure(error), `data_${error.kind}`, error.details.source, error.details.code);
      }
      return fail(
        message("call.failed", {
          tool: call.name,
          reason: errorText(error),
        }),
        "failed",
      );
    } finally {
      context.signal.removeEventListener("abort", stop);
    }
  }

  /**
   * A tool's answer as an outcome: its payload checked against the tool's output schema, recorded
   * (data and compute tools, when the run records), and written by the renderer.
   */
  private recorded(
    call: ToolCall,
    tool: Tool,
    answer: ToolAnswer<unknown>,
    { args, input, inputs }: { args: unknown; input: unknown; inputs: string[] },
    context: ToolContext,
    budget: number,
  ): CallOutcome {
    const checked = (tool.output ?? NO_DATA).safeParse(answer.payload);
    if (!checked.success) {
      return failed(
        message("call.failed", {
          tool: call.name,
          reason: `its data did not fit its contract: ${z.prettifyError(checked.error)}`,
        }),
        "failed",
        undefined,
        budget,
      );
    }
    const payload = checked.data;
    // Named from the arguments as the tool read them and from what came back.
    const label = labelText(tool, args, input, payload, context.clock?.() ?? new Date());
    // A record shown whole again is written as its own tool writes it.
    const writer = answer.as ?? tool;
    const shown = (id?: string) =>
      renderResult({
        ...(id ? { id } : {}),
        tool: call.name,
        label,
        provenance: answer.provenance,
        payload,
        room: Math.min(CALLS.textChars, budget),
        ...(writer.table ? { table: writer.table } : {}),
        ...(writer.render ? { render: writer.render.bind(writer) } : {}),
      });
    const unrecorded = shown();
    const record =
      tool.kind === "control"
        ? undefined
        : context.evidence?.publish({
            call: call.callId,
            tool: call.name,
            args: call.args,
            label,
            payload,
            preview: unrecorded.slice(0, EVIDENCE.previewChars),
            inputs,
            provenance: answer.provenance,
          });
    const text = record ? shown(record.id) : unrecorded;
    const { source, after } = answer.provenance;
    const evidence = record?.id ?? answer.shows;
    // The person watching reads what came back, not the id: the line after the header.
    const summary = summarize(answer.summary ?? unrecorded.split("\n").slice(1).join("\n"));
    // Below the head (its line, the source's, the provenance notes): what the model reads of the data.
    const body = unrecorded
      .split("\n")
      .slice(2 + (answer.provenance.notes?.length ?? 0))
      .join("\n");
    const preview = previewOf(payload, {
      ...(tool.preview ? { specs: tool.preview } : {}),
      text: body,
      summary,
      year: (context.clock?.() ?? new Date()).getUTCFullYear(),
    });
    return {
      ...bounded(text, budget),
      summary,
      ...(preview ? { preview } : {}),
      source: sourceOf({ source, after }),
      ...(evidence ? { evidence } : {}),
      ...(answer.provenance.as_of ? { asOf: answer.provenance.as_of } : {}),
    };
  }
}

/** What a tool that declares no output may answer with: no data at all. */
const NO_DATA = z.never();

/** The text within `budget` characters, the note about the cut included. */
function bounded(text: string, budget: number): { output: string; chars: number; truncated: boolean } {
  if (text.length <= budget) return { output: text, chars: text.length, truncated: false };
  const note = (shown: number) => `\n[cut: ${text.length - shown} of ${text.length} characters not shown]`;
  const shown = Math.max(0, budget - note(budget).length);
  return { output: text.slice(0, shown) + note(shown), chars: text.length, truncated: true };
}

function failed(
  text: string,
  failure: CallFailure,
  source?: string,
  budget: number = CALLS.resultChars,
  code?: string,
): CallOutcome {
  const { output, chars, truncated } = bounded(text, budget);
  return {
    output,
    // What went wrong, on one line: the reason the model read, without the sentence that introduces it.
    summary: summarize(
      oneLineReason(
        failure === "invalid_arguments" ? text.replace(/^The arguments do not fit [^:]+: /, "") : text,
      ),
    ),
    chars,
    truncated,
    failure,
    ...(source ? { source } : {}),
    ...(code ? { code } : {}),
  };
}

/** What the model should understand from a data failure: never an outage passed off as "no data". */
function dataFailure(error: DataError): string {
  const { source } = error.details;
  // Several sources failed, each for its own reason: the message says each one.
  if (error.details.code === "every_source_failed")
    return message("call.everySourceFailed", { detail: error.message });
  switch (error.kind) {
    case "no_data":
      return message("call.noData", { source, detail: error.message });
    case "invalid": {
      const candidates = error.details.candidates?.map((c) => `${c.symbol} (${c.name})`).join(", ");
      return message("call.invalid", {
        source,
        detail: error.message,
        ...(candidates ? { candidates } : {}),
      });
    }
    case "unsupported":
      return message("call.unsupported", { source, detail: error.message });
    case "quota":
      return message("call.quota", {
        source,
        ...(error.details.resetsAt ? { until: error.details.resetsAt } : {}),
      });
    case "rate_limited":
      return message("call.rateLimited", { source });
    case "full":
      return message("call.storageFull", { source });
    case "rejected":
    case "not_configured":
      // A capability no source in this setup offers says so in its own words.
      return error.details.code === "capability_unavailable"
        ? error.message
        : message("call.credentials", { source });
    default:
      return message("call.unreachable", { source, detail: error.message });
  }
}

/** A reason over several lines (a schema error's items and paths) as one line. */
function oneLineReason(text: string): string {
  return text
    .split("\n")
    .map((line) => line.replace(/^\s*[✖→]\s*/, "").trim())
    .filter(Boolean)
    .join("; ");
}

function summarize(text: string): string {
  const first = text.split("\n", 1)[0] ?? "";
  return first.length > 100 ? `${first.slice(0, 99)}…` : first;
}

/** The most characters a call's label takes. */
const LABEL_CHARS = 48;

/** Arguments that page or size a call rather than say what it is about. */
const PAGING = new Set(["after", "skip", "from_line", "limit", "periods"]);

/**
 * The values the model gave for what the tool takes (`known`, the validated arguments), joined in the
 * order given, as the tool reads them: words and numbers, and lists of them; paging left out.
 */
/**
 * The label of a call of `tool` with `args` (references put in place) read as `input`, and its `result`
 * once it has answered.
 */
function labelText(tool: Tool, args: unknown, input: unknown, result?: unknown, now = new Date()): string {
  let text = "";
  try {
    text = tool.label ? tool.label(input, result) : given(args, input as Record<string, unknown>);
  } catch {
    text = given(args, input as Record<string, unknown>);
  }
  const line = datesAsPeopleSayThem(printable(text), now.getUTCFullYear()).replace(/\s+/g, " ").trim();
  return shortened(line, LABEL_CHARS);
}

/** An ISO date, a time after it or not ("2026-06-02", "2026-06-02T23:59:59.999Z"). */
const ISO = String.raw`\d{4}-\d{2}-\d{2}(?:T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?`;

/**
 * A label's dates as the transcript writes them everywhere (preview.ts): "Nov 23", with the year when it is not
 * `year`'s; two side by side (a call's start and end) as a range, "Nov 23 2025 to Jun 2".
 */
function datesAsPeopleSayThem(text: string, year: number): string {
  return text
    .replace(
      new RegExp(`\\b(${ISO})\\s+(${ISO})(?![\\w:.])`, "g"),
      (_, from: string, to: string) => `${dateText(from, year)} to ${dateText(to, year)}`,
    )
    .replace(new RegExp(`\\b${ISO}(?![\\w:.])`, "g"), (date) => dateText(date, year));
}

function given(args: unknown, known: Record<string, unknown>): string {
  if (!args || typeof args !== "object" || Array.isArray(args)) return "";
  return (
    Object.entries(args)
      .filter(([key]) => key in known && !PAGING.has(key))
      // As the tool reads it (a ticker upper-cased), when it reads it as words or numbers.
      .map(([key, value]) => (typeof known[key] === typeof value ? known[key] : value))
      .flatMap((value) =>
        typeof value === "string" || typeof value === "number" || typeof value === "boolean"
          ? [String(value)]
          : Array.isArray(value)
            ? [value.filter((item) => typeof item === "string" || typeof item === "number").join(",")]
            : [],
      )
      .filter(Boolean)
      .join(" ")
  );
}
