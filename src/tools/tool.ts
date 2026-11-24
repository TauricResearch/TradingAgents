// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * What a tool is to the agent loop: a name and description the model reads, an input schema the
 * model's arguments are checked against, and a function the engine runs in a context it sets.
 */
import { z } from "zod";
import type { Clock } from "../contracts/index.js";
import type { EvidenceScope } from "./evidence-store.js";
import type { PreviewSpec } from "./preview.js";
import { ID, NAME_CHARS, referenceTo } from "./references.js";

/**
 * What a call runs with: its cancellation, the run's clock, and the results recorded so far and where its
 * own is recorded (`evidence`). Only `signal` is always there.
 */
export type ToolContext = {
  signal: AbortSignal;
  clock?: Clock;
  evidence?: EvidenceScope;
  /** The id of the call being run, so what it starts (an agent's run) can say which call started it. */
  call?: string;
};

/** Where a result came from and what it describes, recorded with it. */
export type Provenance = {
  /** The source that answered, as the transcript shows it. */
  source: string;
  /** Sources that failed before it. */
  after?: string[];
  /** What the reader must know about the answer (a fallback, say). */
  notes?: string[];
  /** What it describes: a symbol, a pair, a series. */
  subject?: string;
  /** The last date the data describes. */
  as_of?: string;
  /** The data may be copied with a synced session (Tauric's own, or computed from such); else it stays here. */
  syncs?: true;
};

/**
 * A tool the agent loop runs. Its answer is data checked against `output`, recorded (data and compute
 * tools) under an id the model can reference, and rendered to text by one renderer; or, for a control
 * tool, a reply in its own words.
 * - `kind`: data reads a source; compute derives from given values, and its arguments may hold references
 *   ({"ref": "e7", "path": "closes"}), put in place before they are checked; agent is an agent's report;
 *   control keeps the run's books.
 * - `output`: what its data is checked against; a tool that only replies has none.
 * - `table`: the payload's lists written as one table, a column each, in this order.
 * - `render`: the lines written under the result's head, when the tool words its own; they fit in
 *   `room` characters, and a cut says where the rest is (`ref:<id>.<field>`, or the call that pages on).
 */
export type Tool<Input extends z.ZodType = z.ZodType, Output extends z.ZodType = z.ZodType> =
  | (ToolShape<Input, Output> & {
      kind: "data" | "compute" | "agent";
      run(input: z.output<Input>, context: ToolContext): Promise<ToolAnswer<z.output<Output>>>;
    })
  | (ToolShape<Input, Output> & {
      kind: "control";
      run(input: z.output<Input>, context: ToolContext): Promise<ToolAnswer<z.output<Output>> | ToolReply>;
    });

/** What every tool declares besides its kind and run. */
type ToolShape<Input extends z.ZodType, Output extends z.ZodType> = {
  name: string;
  description: string;
  input: Input;
  output?: Output;
  parallelSafe: boolean;
  table?: readonly string[];
  /**
   * A call in a few words for people ("NVDA income statement, quarterly"), naming what it is about as a
   * reader knows it: references arrive as the results they name, and `result` is what came back once the
   * call has answered (an article's headline rather than its id). The arguments given, joined, when unset.
   */
  label?(input: z.output<Input>, result?: z.output<Output>): string;
  render?(payload: z.output<Output>, at: { id?: string; room: number }): string[];
  /**
   * What a result's preview shows (preview.ts): hints made with `hint`, the first whose schema the payload
   * fits; without one, the first lines of the text the model reads.
   */
  preview?: readonly PreviewSpec[];
};

export type ToolAnswer<Payload> = {
  payload: Payload;
  provenance: Provenance;
  /** One line for the person watching, without the result's id; the payload's first line if unset. */
  summary?: string;
  /** The recorded result this one shows again (the evidence tool), when it is not recorded itself. */
  shows?: string;
  /** How the payload is written when it is another tool's (a record shown whole again). */
  as?: Pick<Tool, "table" | "render">;
};

/**
 * A control tool's reply in its own words ("Saved.", a skill's text): the model reads `text` as it is,
 * and nothing is recorded, so it has no head, no id and no provenance.
 */
type ToolReply = {
  text: string;
  /** One line for the person watching; the text's first line if unset. */
  summary?: string;
  /**
   * The run ends after this step, with this as its closing message: the person replies next (a question
   * asked of them). The step's other calls still run.
   */
  ends?: string;
};

/** Declare a tool, keeping its types for `run`. */
export function defineTool<Input extends z.ZodType, Output extends z.ZodType>(
  tool: Tool<Input, Output>,
): Tool<Input, Output> {
  return tool;
}

const REFERENCE = z
  .object({
    ref: z.string().regex(ID).describe("The result's id"),
    path: z
      .string()
      .optional()
      .describe("A part of its data, such as closes or closes[-1]; all of it when left out"),
  })
  .strict()
  .describe(
    `a reference to an earlier result's data, such as ${referenceTo("e7", "closes")} or ${referenceTo("e7", "closes[-1]")}`,
  );

/** A value the model may give directly or as a reference to an earlier result. */
export function refable<T extends z.ZodType>(schema: T) {
  return z.union([schema, REFERENCE]);
}

/** The properties the model is shown for each `wholeResult`. */
const WHOLE = new WeakMap<object, Record<string, unknown>>();

/**
 * An earlier result taken whole, `what` saying which (such as "A price_history result"), and with `named`
 * a label that names it in the tool's output. References are put in place before arguments are checked,
 * so the check reads the result's record; the model is shown the form it writes, {"ref": "e7"} with no
 * path (see `inputSchema`).
 */
export function wholeResult(what: string, { named = false }: { named?: boolean } = {}) {
  const schema = z
    .record(z.string(), z.unknown())
    .describe(
      named
        ? `${what}, referenced whole: ${referenceTo("e7")}, or with a name for it, {"ref":"e7","label":"NVDA"}`
        : `${what}, referenced whole: ${referenceTo("e7")}`,
    );
  WHOLE.set(schema, {
    ref: { type: "string", pattern: ID.source, description: "The result's id" },
    ...(named
      ? {
          label: {
            type: "string",
            minLength: 1,
            maxLength: NAME_CHARS,
            description: "A name for it, such as its symbol",
          },
        }
      : {}),
  });
  return schema;
}

/** The JSON Schema of a tool's arguments, as the model reads it. */
export function inputSchema(tool: Pick<Tool, "input">): Record<string, unknown> {
  return z.toJSONSchema(tool.input, {
    io: "input",
    override: ({ zodSchema, jsonSchema }) => {
      const properties = WHOLE.get(zodSchema);
      if (!properties) return;
      const { description } = jsonSchema;
      for (const key of Object.keys(jsonSchema)) delete (jsonSchema as Record<string, unknown>)[key];
      Object.assign(jsonSchema, {
        type: "object",
        properties,
        required: ["ref"],
        additionalProperties: false,
        description,
      });
    },
  });
}

/**
 * A tool's refusal to answer as asked (a price series asked of a tool that reads values, say). The call
 * counts as failed, and the message tells the model what it can do instead.
 */
export class ToolRefusalError extends Error {
  override readonly name = "ToolRefusalError";
}
