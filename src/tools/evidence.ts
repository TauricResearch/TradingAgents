// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/** A recorded result again, whole or one field of it: what a result cut to fit the context still holds. */
import { z } from "zod";
import { AGENT_TOOL } from "../contracts/index.js";
import { ID, PATH, resolveReferences } from "./references.js";
import { renderReport } from "./report.js";
import { defineTool, type Tool, ToolRefusalError } from "./tool.js";

export type Writer = Pick<Tool, "table" | "render">;

/** How each of `tools` writes its results, and how an agent's report is written. */
export function writersOf(tools: readonly Tool[]): Map<string, Writer> {
  return new Map([
    [AGENT_TOOL, { render: renderReport as NonNullable<Tool["render"]> }],
    ...tools.map((tool): [string, Writer] => [
      tool.name,
      {
        ...(tool.table ? { table: tool.table } : {}),
        ...(tool.render ? { render: tool.render.bind(tool) } : {}),
      },
    ]),
  ]);
}

/** `tools`: the tools whose records it may show, each written again as its tool writes it. */
export function evidenceTool(tools: readonly Tool[] = []) {
  const writers = writersOf(tools);
  return defineTool({
    name: "evidence",
    description:
      "Show a recorded result again by its id (e7), with where it came from: all of it, or one part with a path " +
      "such as closes or closes[-1]. Use it for a result cut to fit the context.",
    kind: "control",
    parallelSafe: true,
    input: z.object({
      id: z.string().regex(ID).describe("The result's id, such as e7"),
      path: z.string().regex(PATH).optional().describe("A part of it, such as closes or closes[-1]"),
    }),
    output: z.unknown(),
    label: ({ id, path }) => (path ? `${id} ${path}` : id),
    async run({ id, path }, { evidence }) {
      if (!evidence) throw new ToolRefusalError(`There is no recorded result ${id}.`);
      const record = evidence.get(id);
      // Read as a reference from this call's step: a result of the same step had not been seen.
      const resolved = resolveReferences({ ref: id, ...(path ? { path } : {}) }, evidence, evidence);
      if (!resolved.ok) {
        if (record?.local_only && record.payload === undefined) {
          throw new ToolRefusalError(`${resolved.error}\nIts preview:\n${record.preview}`);
        }
        throw new ToolRefusalError(resolved.error);
      }
      if (!record) throw new ToolRefusalError(`There is no recorded result ${id}.`);
      const value = resolved.value;
      const writer = path ? undefined : writers.get(record.tool);
      return {
        payload: path ? { [path]: value } : value,
        provenance: {
          ...record.provenance,
          notes: [...(record.provenance.notes ?? []), `recorded from ${record.tool}`],
        },
        summary: `${path ? `${id} ${path}` : id} from ${record.tool}`,
        shows: id,
        ...(writer ? { as: writer } : {}),
      };
    },
  });
}
