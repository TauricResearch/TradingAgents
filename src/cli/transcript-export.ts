// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The whole transcript as Markdown: every question, what the main agent thought (while this terminal still holds
 * it), every call with its result or failure, each sub-agent's gist, and the answers as written. `/export`
 * writes it to a file.
 */

import { APP_TITLE, message, type Preview, printable, sourceLine } from "../contracts/index.js";
import { listMarkdown } from "./list.js";
import { previewLines } from "./preview-rows.js";
import { shortDuration } from "./rows.js";
import { type AgentMember, type Block, groupSources } from "./transcript-state.js";

/** Model or source text kept literal in Markdown: its markup characters escaped. */
function literal(text: string): string {
  return text
    .replace(/[\\`*_[\]()#+!>|~<]/g, (char) => `\\${char}`)
    .replace(/^(\s*)(\d+)\./gm, "$1$2\\.")
    .replace(/^(\s*)-/gm, "$1\\-");
}

/** A value on one line, for a list item: line breaks and runs of spaces as one space, kept literal. */
function flat(text: string): string {
  return literal(printable(text).replace(/\s+/g, " ").trim());
}

/** A call or agent as a list item: its mark, what it was, then what came of it. */
function item(failed: boolean | undefined, what: string, result: string, detail: string[]): string {
  const extra = detail.filter(Boolean);
  return `- ${failed ? "✗" : "✓"} ${flat(what)}${result ? `: ${flat(result)}` : ""}${extra.length ? ` (${extra.join(", ")})` : ""}`;
}

/** A call's preview under its item, every row of it, in columns as the transcript sets them. */
function previewed(preview: Preview | undefined, indent = ""): string[] {
  if (!preview) return [];
  return previewLines(preview, { width: Number.POSITIVE_INFINITY, rows: preview.rows.length }).map(
    (line) => `${indent}  ${literal(line.text)}${line.more ? `  ${literal(line.more)}` : ""}`,
  );
}

function section(block: Block): string | undefined {
  switch (block.kind) {
    case "header":
      return `# ${APP_TITLE} ${flat(block.version)}\n\n${flat(block.model)} | ${message(block.keyed ? "app.dataTauric" : "app.dataYahoo")}`;
    case "question":
      return `## › ${literal(printable(block.text)).split("\n").join("\n   ")}`;
    case "lines":
      return [
        ...block.lines.map((line) => `    ${printable(line)}`),
        ...(block.links
          ? [`    ${block.links.map((link) => `${printable(link.text)} (${link.url})`).join(" | ")}`]
          : []),
      ].join("\n");
    case "message": {
      // An answer that left a code block open (it was stopped) is closed, so it cannot swallow what follows.
      const text = printable(block.text).trim();
      const open = ((text.match(/^ {0,3}(?:```|~~~)/gm) ?? []).length & 1) === 1;
      return open ? `${text}\n\u0060\u0060\u0060` : text;
    }
    case "list":
      return [
        ...listMarkdown(block.list).map((line) => printable(line)),
        ...(block.links
          ? ["", block.links.map((link) => `${printable(link.text)} (${link.url})`).join(" | ")]
          : []),
      ].join("\n");
    case "sources":
      return [
        message("answer.sources"),
        "",
        ...block.sources.map((source) => `- ${printable(sourceLine(source))}`),
      ].join("\n");
    case "thought": {
      const heading = `> _${message("app.thoughtFor", { durationMs: block.durationMs })}_`;
      const text = printable(block.text).trim();
      return text
        ? `${heading}\n>\n${text
            .split("\n")
            .map((line) => (line ? `> ${line}` : ">"))
            .join("\n")}`
        : heading;
    }
    case "tool": {
      const what = [block.name, block.label].filter(Boolean).join(" ");
      const elapsed = block.elapsedMs !== undefined ? shortDuration(block.elapsedMs) : "";
      const preview = block.failed ? undefined : block.preview;
      return [
        item(block.failed, what, preview?.replacesSummary ? "" : block.summary, [
          block.source ?? "",
          block.agent ?? "",
          elapsed,
        ]),
        ...previewed(preview),
      ].join("\n");
    }
    case "group":
      return [
        item(
          false,
          message("app.fetched", { count: block.calls.length, sources: groupSources(block.calls) }),
          "",
          [block.elapsedMs !== undefined ? shortDuration(block.elapsedMs) : ""],
        ),
        ...block.calls.flatMap((call) => [
          `  ${item(
            call.failed,
            [call.name, call.label].filter(Boolean).join(" "),
            call.failed || call.preview?.replacesSummary ? (call.reason ?? "") : (call.summary ?? ""),
            [call.source ?? "", call.elapsedMs !== undefined ? shortDuration(call.elapsedMs) : ""],
          )}`,
          ...previewed(call.failed ? undefined : call.preview, "  "),
        ]),
      ].join("\n");
    case "agents": {
      // The full transcript: each agent, what it was asked and found, and every call it made.
      const member = (one: AgentMember, indent: string) => {
        const detail = [
          one.calls ? message("app.toolCount", { count: one.calls }) : "",
          one.elapsedMs !== undefined ? shortDuration(one.elapsedMs) : "",
        ];
        return [
          `${indent}${item(one.status !== "done", one.label, one.summary, detail)}`,
          ...(one.title ? [`${indent}  - ${flat(one.title)}`] : []),
          ...(one.reason ? [`${indent}  - ${flat(one.reason)}`] : []),
          ...(one.status === "stopped" ? [`${indent}  - ${message("app.agentStopped")}`] : []),
          ...(one.tools ?? []).map((tool) => `${indent}  - ✓ ${flat(tool)}`),
          ...(one.failures ?? []).map((failure) => `${indent}  - ✗ ${flat(failure)}`),
        ];
      };
      if (block.members.length === 1) return member(block.members[0] as AgentMember, "").join("\n");
      const failed = block.members.filter((one) => one.status === "failed").length;
      const stopped = block.members.every((one) => one.status === "stopped");
      return [
        item(
          stopped,
          message(stopped ? "app.agentsStopped" : "app.agentsFinished", { count: block.members.length }),
          failed && !stopped ? message("app.failedCount", { count: failed }) : "",
          [block.elapsedMs !== undefined ? shortDuration(block.elapsedMs) : ""],
        ),
        ...block.members.flatMap((one) => member(one, "  ")),
      ].join("\n");
    }
    case "notice":
      return `_${flat(block.text)}_`;
    case "turnEnd":
      return `_${[
        message("app.worked", { durationMs: block.durationMs }),
        message("app.tokensIn", { count: block.inputTokens }),
        message("app.tokensOut", { count: block.outputTokens }),
        ...(block.plan ? [message("app.planCount", block.plan)] : []),
      ].join(", ")}_`;
  }
}

/**
 * The last answer in `done` as Markdown: its text with citations numbered as the transcript shows them, then
 * the sources it cited; undefined when no turn has ended with an answer.
 */
export function lastAnswerMarkdown(done: readonly Block[]): string | undefined {
  const last = done.findLast((block) => block.kind === "turnEnd" && block.answered.answer.trim() !== "");
  if (last?.kind !== "turnEnd") return undefined;
  const { answer, sources } = last.answered;
  const listed = sources.map((source) => `- ${printable(sourceLine(source))}`);
  return [
    printable(answer).trim(),
    ...(listed.length ? [message("answer.sources"), listed.join("\n")] : []),
  ].join("\n\n");
}

/** The finished blocks as one Markdown document; rows of a kind that sit together stay together. */
export function transcriptMarkdown(done: readonly Block[]): string {
  const parts: string[] = [];
  for (const block of done) {
    const text = section(block);
    if (text === undefined || text === "") continue;
    // Consecutive list items (calls, groups, agents) form one list; anything else is its own paragraph.
    const listed = block.kind === "tool" || block.kind === "group" || block.kind === "agents";
    const previous = parts.at(-1);
    if (listed && previous?.startsWith("- ")) parts[parts.length - 1] = `${previous}\n${text}`;
    else parts.push(text);
  }
  return `${parts.join("\n\n")}\n`;
}
