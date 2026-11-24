// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * The inline transcript. Finished blocks are written once into the terminal's scrollback through
 * <Static>; only the live region below them is redrawn. The live region always fits the window:
 * Ink can erase and redraw only the rows still on screen, so a taller region would leave copies of
 * itself in the scrollback. A streaming answer's final parts go to the scrollback as they are written,
 * so the live region holds only what may still change.
 */
import { Box, Static, Text, useWindowSize } from "ink";
import { useEffect, useState } from "react";
import stringWidth from "string-width";
import wrapAnsi from "wrap-ansi";
import {
  AGENT_TOOL,
  message,
  numberCitations,
  type Preview,
  printable,
  sourceLine,
} from "../contracts/index.js";
import { hyperlink } from "./links.js";
import { listColumn } from "./list.js";
import { answerRows, liveHold, liveSource } from "./markdown.js";
import { alignRows, PREVIEW_NARROW, PREVIEW_ROWS, previewLines } from "./preview-rows.js";
import {
  after,
  besideMeta,
  type Column,
  type Field,
  named,
  oneLine,
  SEPARATOR,
  SPINNER_MS,
  shortDuration,
  spinnerFrame,
  TABLE_GAP,
  tableRow,
  tableWidths,
} from "./rows.js";
import { agentColour, type Theme } from "./theme.js";
import { useRoles, useTheme } from "./theme-context.js";
import {
  type AgentMember,
  type Block,
  type GroupedCall,
  gapBefore,
  groupSources,
  liveMarkdown,
  pendingThought,
  type TranscriptState,
} from "./transcript-state.js";
import { Welcome } from "./Welcome.js";

/** A citation the text ends in before its closing bracket (`[e1`, `[e3, e`). */
const PARTIAL_CITATION = /[ \t]*\[(?:e\d*(?:\s*,\s*)?)*$/;

/** Most running tools and agents listed one per row; the rest are counted on one more row. */
const LIVE_ACTIVITY_LINES = 6;
/** Most steps of the main agent's plan shown while its turn runs. */
const LIVE_PLAN_LINES = 6;

/** Text without blank lines before or after it; spaces within lines stay as written. */
function withoutBlankEdges(text: string): string {
  return text.replace(/^(?:[ \t]*\n)+/, "").replace(/(?:\n[ \t]*)+$/, "");
}

/** A finished block; `columns`: the window's width when it is written (rows are fitted to it). */
function BlockView({ block, columns }: { block: Block; columns: number }) {
  const { unicode, shade } = useTheme();
  const roles = useRoles();
  const body = (() => {
    switch (block.kind) {
      case "header":
        return (
          <Welcome
            version={block.version}
            model={block.model}
            keyed={block.keyed}
            news={block.news}
            columns={columns}
          />
        );
      case "question": {
        // A block of its own across the window: shaded where the background is known, else the text in
        // bold; a blank row above and below either way. Lines after the first sit under the text.
        const rows = block.text.split("\n").map((line, index) => (
          // A wrapped line stays under the text, not under the prompt.
          // biome-ignore lint/suspicious/noArrayIndexKey: the lines of one finished block never change
          <Box key={index}>
            <Box width={2} flexShrink={0}>
              <Text {...roles.detail}>{index === 0 ? "›" : ""}</Text>
            </Box>
            <Text bold={!shade}>{printable(line) || " "}</Text>
          </Box>
        ));
        return (
          <Box
            flexDirection="column"
            paddingY={1}
            width={columns}
            {...(shade ? { backgroundColor: shade } : {})}
          >
            {rows}
          </Box>
        );
      }
      case "message":
        // Laid out here, row by row, exactly as the live region showed it.
        return (
          <Box flexDirection="column">
            {answerRows(withoutBlankEdges(block.text), { columns, unicode, lead: block.lead === true }).map(
              (row, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: the rows of one finished block never change
                <Text key={index} wrap="truncate">
                  {row || " "}
                </Text>
              ),
            )}
          </Box>
        );
      case "lines":
        // As wide as the window, so a wrapped row wraps here, under its column, not again in the terminal.
        return (
          <Box flexDirection="column" paddingLeft={2} width={columns}>
            {block.lines.map((line, index) => {
              // An item ("- text") wraps under its text, not under its bullet; a row of a list ("name  what it
              // does", "/help  commands and keys") under its second column, never back at the margin.
              const item = /^(\s*- )(.*)$/.exec(line) ?? /^(\s*\S+\s{2,})(\S.*)$/.exec(line);
              return item ? (
                // biome-ignore lint/suspicious/noArrayIndexKey: the lines of one finished block never change
                <Box key={index}>
                  <Box width={stringWidth(printable(item[1] as string))} flexShrink={0}>
                    <Text>{printable(item[1] as string)}</Text>
                  </Box>
                  <Text>{printable(item[2] as string)}</Text>
                </Box>
              ) : (
                // biome-ignore lint/suspicious/noArrayIndexKey: the lines of one finished block never change
                <Text key={index}>{printable(line) || " "}</Text>
              );
            })}
            {block.links ? (
              <Text wrap="truncate">
                {block.links
                  .map((link) => hyperlink(printable(link.text), link.url, unicode))
                  .join(SEPARATOR)}
              </Text>
            ) : null}
          </Box>
        );
      case "list":
        return <ListBlock block={block} columns={columns} unicode={unicode} />;
      case "agents":
        return <AgentGroup block={block} columns={columns} />;
      case "tool": {
        // The mark in the gutter; the name and what it was asked; the result; source and time at the right.
        const failed = block.failed === true;
        const indent = block.nested ? 2 : 0;
        const head = printable(block.name);
        const elapsed = block.elapsedMs !== undefined ? shortDuration(block.elapsedMs) : "";
        const width = Math.max(10, columns - indent - 2);
        const markText = mark(failed, unicode);
        const markColour = failed ? roles.error : roles.success;
        const child = unicode ? "⎿" : "\\";
        {
          const meta = [oneLine(block.source ?? ""), elapsed].filter(Boolean).join(" ");
          // A preview that says all the summary does takes its place under the row.
          const preview = failed ? undefined : block.preview;
          const summary = preview?.replacesSummary ? "" : oneLine(block.summary);
          const laid = besideMeta(
            [
              { text: head, shrink: 0 },
              { text: oneLine(block.label ?? ""), shrink: 1.5, gap: " " },
              { text: failed ? "" : summary, shrink: 2 },
            ],
            meta,
            width,
          );
          const [name = head, label = "", result = ""] = laid.fields;
          return (
            <Box flexDirection="column">
              <Text wrap="truncate">
                {" ".repeat(indent)}
                <Text {...markColour}>{markText}</Text> <Text>{name}</Text>
                {label ? <Text {...roles.detail}> {label}</Text> : null}
                {result ? <Text {...roles.detail}>{`${SEPARATOR}${result}`}</Text> : null}
                {laid.meta ? <Text {...roles.detail}>{`${" ".repeat(laid.gap)}${laid.meta}`}</Text> : null}
              </Text>
              {failed ? (
                <Text {...roles.error} wrap="truncate">
                  {" ".repeat(indent + 2)}
                  {child} {summary}
                </Text>
              ) : summary && !result ? (
                // The result did not fit beside the source and time: under the row instead.
                <Text {...roles.detail} wrap="truncate">
                  {" ".repeat(indent + 2)}
                  {child} {summary}
                </Text>
              ) : null}
              {preview
                ? previewLines(preview, {
                    width: Math.max(10, columns - indent - 4),
                    rows: columns < PREVIEW_NARROW ? 1 : PREVIEW_ROWS,
                  }).map((line, index) => (
                    // biome-ignore lint/suspicious/noArrayIndexKey: the lines of one finished block never change
                    <Text key={index} {...roles.detail} wrap="truncate">
                      {" ".repeat(indent + 2)}
                      {index === 0 && !(summary && !result) ? child : " "} {line.text}
                      {line.more ? `  ${line.more}` : ""}
                    </Text>
                  ))
                : null}
            </Box>
          );
        }
      }
      case "group": {
        // The step's calls in one row: how many, how many failed, the slowest one's time at the right; under
        // it each call, then each failure's reason.
        const failures = block.calls.filter((call) => call.failed);
        const elapsed = block.elapsedMs !== undefined ? shortDuration(block.elapsedMs) : "";
        const width = Math.max(10, columns - 2);
        const laid = besideMeta(
          [
            {
              text: message("app.fetched", { count: block.calls.length, sources: groupSources(block.calls) }),
              shrink: 0,
            },
            {
              text: failures.length ? message("app.failedCount", { count: failures.length }) : "",
              shrink: 1,
            },
          ],
          elapsed,
          width,
        );
        const [head = "", failedText = ""] = laid.fields;
        const cross = mark(true, unicode);
        const what = (call: (typeof block.calls)[number]) => oneLine(named(call.name, call.label ?? ""));
        // With previews, each call on a row of its own: what it was, then its preview's first row, in columns.
        const previewed = block.calls.some((call) => call.preview && !call.failed);
        const memberRows = previewed
          ? groupRows(block.calls, (call) => (call.failed ? `${cross} ${what(call)}` : what(call)))
          : [];
        return (
          <Box flexDirection="column">
            <Text wrap="truncate">
              <Text {...roles.success}>{mark(false, unicode)}</Text> <Text {...roles.title}>{head}</Text>
              {failedText ? <Text {...roles.error}>{`${SEPARATOR}${failedText}`}</Text> : null}
              {laid.meta ? <Text {...roles.detail}>{`${" ".repeat(laid.gap)}${laid.meta}`}</Text> : null}
            </Text>
            {previewed ? (
              memberRows.map((row, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: the lines of one finished block never change
                <Text key={index} {...roles.detail} wrap="truncate">
                  {"  "}
                  {index === 0 ? (unicode ? "⎿" : "\\") : " "} {row}
                </Text>
              ))
            ) : (
              <Text {...roles.detail} wrap="truncate">
                {"  "}
                {unicode ? "⎿" : "\\"}{" "}
                {block.calls.map((call) => (call.failed ? `${cross} ${what(call)}` : what(call))).join(", ")}
              </Text>
            )}
            {failures.map((call, index) => (
              // biome-ignore lint/suspicious/noArrayIndexKey: the lines of one finished block never change
              <Text key={index} {...roles.error} wrap="truncate">
                {"    "}
                {cross} {what(call)}: {oneLine(call.reason ?? "")}
              </Text>
            ))}
          </Box>
        );
      }
      case "sources":
        // Under the answer, at its text's column, quiet.
        return (
          <Box flexDirection="column" paddingLeft={2}>
            <Text {...roles.detail}>{message("answer.sources")}</Text>
            {block.sources.map((source) => (
              <Text key={source.id} {...roles.detail} wrap="truncate">
                {printable(sourceLine(source))}
              </Text>
            ))}
          </Box>
        );
      case "notice": {
        // At the transcript's left edge: its glyph (if any) in the gutter, its words at column 2, wrapped there.
        const role = roles[block.level === "error" ? "error" : block.level === "warn" ? "warning" : "detail"];
        return (
          <Box width={columns}>
            <Box width={2} flexShrink={0}>
              <Text {...role}>{block.context ? (unicode ? "↻" : "~") : ""}</Text>
            </Box>
            <Text {...role}>{printable(block.text)}</Text>
          </Box>
        );
      }
      case "thought":
        // What is kept of a thought: its first and last lines, a row each, under its rule, the lines between
        // as "…" (the whole of it is in /export); then how long it took.
        return (
          <Box flexDirection="column">
            {block.lines
              ? keptThought(
                  { lines: block.lines, ...(block.omitted ? { omitted: block.omitted } : {}) },
                  columns,
                  unicode,
                ).map((row, index) => (
                  // biome-ignore lint/suspicious/noArrayIndexKey: the rows of one finished block never change
                  <Text key={index} {...roles.detail} italic wrap="truncate">
                    {row}
                  </Text>
                ))
              : null}
            <Text {...roles.detail} wrap="truncate">
              {unicode ? "∴ " : ": "}
              {message("app.thoughtFor", { durationMs: block.durationMs })}
            </Text>
          </Box>
        );
      case "turnEnd":
        return (
          <Text {...roles.detail}>
            {"  "}
            {[
              message("app.worked", { durationMs: block.durationMs }),
              message("app.tokensIn", { count: block.inputTokens }),
              message("app.tokensOut", { count: block.outputTokens }),
              ...(block.plan ? [message("app.planCount", block.plan)] : []),
            ].join(SEPARATOR)}
          </Text>
        );
    }
  })();
  return block.gap ? <Box marginTop={block.gap}>{body}</Box> : body;
}

/** A finished row's mark: a check, or a cross when it failed (ASCII stand-ins where needed). */
function mark(failed: boolean, unicode: boolean): string {
  if (!unicode) return failed ? "x" : "+";
  return failed ? "✗" : "✓";
}

/** Thinking as rows: two cells in, each wrapped row behind a rule. */
function thinkingRows(text: string, columns: number, unicode: boolean): string[] {
  const rule = unicode ? "│" : "|";
  return tailRows(printable(text), Math.max(1, columns - 4), Number.MAX_SAFE_INTEGER).map((row) => {
    const shown = row.trimEnd();
    return shown ? `  ${rule} ${shown}` : `  ${rule}`;
  });
}

/** A finished thought's rows: its first line, "…" for the lines between, its last line, each one row. */
function keptThought(
  block: { lines: readonly string[]; omitted?: number },
  columns: number,
  unicode: boolean,
): string[] {
  const row = (line: string) => thinkingRows(line, columns, unicode)[0] ?? "";
  const [first, ...rest] = block.lines.map(row);
  const rule = unicode ? "│" : "|";
  return [...(first ? [first] : []), ...(block.omitted ? [`  ${rule} …`] : []), ...rest];
}

/** The last `rows` rows of `text` as the terminal wraps it at `columns` (the way Ink wraps it). */
function tailRows(text: string, columns: number, rows: number): string[] {
  if (!text || rows <= 0) return [];
  return wrapAnsi(text, Math.max(1, columns), { trim: false, hard: true }).split("\n").slice(-rows);
}

/**
 * One row of the live region: an optional glyph (the spinner, a plan mark) in the accent, the row's name
 * in the default colour, then the rest, dim unless it is answer text.
 */
type LiveLine = {
  key: string;
  text: string;
  /** `detail` for secondary rows; answer text keeps the default look. */
  role?: "detail";
  /** `spins`: the spinner, which moves while the row is shown; `detail`: a quiet mark (an agent's `⎿`). */
  glyph?: { text: string; accent: boolean; spins?: boolean; detail?: boolean };
  /** A state mark before the head (an agent's ✗, or its ✓ when `markDone`). */
  mark?: string;
  markDone?: boolean;
  head?: string;
  /** The agent the head names (its catalog name): the head is in that agent's colour, bold. */
  headAgent?: string;
  /** The head's role: a block's heading (the plan's) is a title. */
  headRole?: "title";
  /** Where the row starts: at the gutter (0), or after `indent` cells; activity rows start at 2. */
  indent?: number;
  italic?: boolean;
  /** Text after `text`, each part in its own role (the default text when none): an agent's call under way. */
  tail?: { text: string; role?: "detail" }[];
};

/**
 * Most rows of the thinking under way the live region shows (its last ones): a third of the window, at least six.
 * When it ends, the scrollback keeps its first and last lines.
 */
function liveThinkingRows(rows: number): number {
  return Math.max(6, Math.floor(rows / 3));
}

/**
 * A running row: its moving mark in the gutter (`indent` cells in), its name (and its label after it, when
 * `labelled`), its other fields, and `meta` (its time) at the right, fitted into the window.
 */
function runningLine(
  key: string,
  glyph: NonNullable<LiveLine["glyph"]>,
  head: string,
  fields: Field[],
  meta: string,
  columns: number,
  labelled = false,
): LiveLine {
  const [first, ...more] = fields;
  const joined = labelled && first ? [{ ...first, gap: " " }, ...more] : fields;
  const laid = besideMeta([{ text: head, shrink: 0 }, ...joined], meta, Math.max(1, columns - 2));
  const [name = head, ...rest] = laid.fields;
  const [label = "", ...others] = labelled ? rest : ["", ...rest];
  return {
    key,
    indent: 0,
    glyph,
    head: named(name, label),
    text: `${after(others)}${laid.meta ? `${" ".repeat(laid.gap)}${laid.meta}` : ""}`,
    role: "detail" as const,
  };
}

/** A time worth showing on a running row: from a second on. */
function runningFor(startedAt: number, now: number): string {
  const ms = now - startedAt;
  return ms >= 1_000 ? shortDuration(ms) : "";
}

/**
 * Every row of the live region, fitted into `rows - 1` (the last row is where the cursor waits). `now`
 * moves the spinner and the times; `unicode` picks the glyphs.
 */
export function liveLines(
  state: TranscriptState,
  columns: number,
  rows: number,
  now = Date.now(),
  unicode = true,
): LiveLine[] {
  let free = Math.max(0, rows - 1);
  const take = (wanted: number) => {
    const granted = Math.max(0, Math.min(wanted, free));
    free -= granted;
    return granted;
  };
  const frame = spinnerFrame(now, unicode);
  // Citations numbered as they will be written; one still being typed waits for its bracket.
  const text = numberCitations(
    liveMarkdown(state.live).replace(/^\n+/, "").replace(PARTIAL_CITATION, ""),
    state.citations.cited,
  );
  const firstTextRow = text ? take(1) : 0;
  // The main agent's thinking: its newest rows (after what else must show), then its header at the gutter,
  // which becomes the "Thought for" line when the thinking ends.
  const thinkingHeader: LiveLine[] =
    state.live.thinking && take(1)
      ? [
          {
            key: "thinking",
            indent: 0,
            glyph: { text: unicode ? "∴" : ":", accent: false },
            role: "detail" as const,
            // No time here: the status row's is the turn's one timer.
            text: message("app.thinkingHeader"),
          },
        ]
      : [];

  const marks = unicode
    ? { pending: "[ ]", active: "[›]", done: "[✓]", skipped: "[-]" }
    : { pending: "[ ]", active: "[>]", done: "[x]", skipped: "[-]" };
  // The plan, a block of its own: its heading at the blocks' left edge (column 2), as every block heading is,
  // its steps' marks there too, the active step in the title role.
  const plan: LiveLine[] = state.live.plan.map((step, index) => ({
    key: `plan:${index}`,
    indent: 2,
    glyph: { text: marks[step.status], accent: step.status === "active" },
    ...(step.status === "done" || step.status === "skipped"
      ? { role: "detail" as const }
      : step.status === "active"
        ? { head: printable(step.text), headRole: "title" as const }
        : {}),
    text: step.status === "active" ? "" : printable(step.text),
  }));
  const counted = state.live.plan.filter((step) => step.status !== "skipped");
  // The running mark: the spinner.
  const moving: NonNullable<LiveLine["glyph"]> = { text: frame, accent: true, spins: true };
  // Each running sub-agent: its header, then what it is doing now (up to three of its running calls, or
  // its latest one). The main agent's own running calls are rows of their own; its calls to sub-agents are the
  // agents' rows.
  const entries: { header: LiveLine; children: LiveLine[] }[] = [
    ...agentEntries(state, moving, columns, now, unicode),
    ...state.live.tools
      .filter((tool) => !tool.nested && tool.name !== AGENT_TOOL)
      .map((tool) => ({
        header: runningLine(
          JSON.stringify(["tool", tool.run, tool.call]),
          moving,
          printable(tool.name),
          [{ text: oneLine(tool.label ?? ""), shrink: 2 }],
          runningFor(tool.startedAt, now),
          columns,
          true,
        ),
        children: [],
      })),
  ];
  // The thinking under way comes before the plan, and takes only the rows it draws, with the blank row the
  // thought block will have above it.
  const pending = thinkingHeader.length ? pendingThought(state.live) : "";
  const reasoningRows = pending ? thinkingRows(pending, columns, unicode).slice(-liveThinkingRows(rows)) : [];
  const thinkingGap =
    thinkingHeader.length && gapBefore(state.done.at(-1), { kind: "thought" }) ? take(1) : 0;
  const tailGrant = take(reasoningRows.length);
  const thought: LiveLine[] = [
    ...(thinkingGap ? [{ key: "thought:gap", text: "" }] : []),
    ...(tailGrant ? reasoningRows.slice(-tailGrant) : []).map((row, index) => ({
      key: `thought:${index}`,
      indent: 0,
      italic: true,
      role: "detail" as const,
      text: row,
    })),
  ];
  // A blank row and the heading, then as many steps as fit (from just before the first active one), and
  // how many more there are.
  const planHead =
    plan.length && take(2) === 2
      ? [
          { key: "plan:gap", text: "" },
          {
            key: "plan:head",
            indent: 2,
            head: message("app.planHeading"),
            headRole: "title" as const,
            role: "detail" as const,
            text: `  ${message("app.planDone", { done: counted.filter((step) => step.status === "done").length, total: counted.length })}`,
          },
        ]
      : [];
  const room = planHead.length ? take(Math.min(plan.length, LIVE_PLAN_LINES)) : 0;
  const active = Math.max(
    0,
    state.live.plan.findIndex((step) => step.status === "active"),
  );
  const from = Math.max(0, Math.min(active - 1, plan.length - room));
  const cut = plan.length > room && room > 1;
  const steps = plan.slice(from, from + (cut ? room - 1 : room));
  const shownPlan = [
    ...planHead,
    ...steps,
    ...(cut
      ? [
          {
            key: "plan:more",
            indent: 2,
            role: "detail" as const,
            text: message("app.planMore", { count: plan.length - steps.length }),
          },
        ]
      : []),
  ];
  // The plan and what runs are blocks of their own: a blank row between them.
  const planGap = shownPlan.length && entries.length ? take(1) : 0;
  // Every header first (a count of the rest when they do not all fit), then the children with the rows left.
  const headerRows = take(Math.min(entries.length, LIVE_ACTIVITY_LINES));
  const shownEntries = entries.slice(
    0,
    entries.length > headerRows ? Math.max(0, headerRows - 1) : headerRows,
  );
  const more: LiveLine[] =
    entries.length > headerRows && headerRows > 0
      ? [
          {
            key: "more",
            role: "detail" as const,
            text: message("app.moreRunning", { count: entries.length - shownEntries.length }),
          },
        ]
      : [];
  // Running rows with nothing live above them: the blank row their finished block will have, so they do
  // not move when it is written.
  const above = thought.length + thinkingHeader.length + shownPlan.length + (text ? 1 : 0);
  const entryGap =
    !planGap &&
    !above &&
    entries.length &&
    // A call or an agent group is a block of its own after anything but the question (see gapBefore).
    state.done.length > 0 &&
    !["header", "question"].includes(state.done.at(-1)?.kind ?? "")
      ? take(1)
      : 0;
  const listed = [
    ...(planGap ? [{ key: "plan:after", text: "" }] : []),
    ...(entryGap ? [{ key: "entries:gap", text: "" }] : []),
    ...shownEntries.flatMap((entry) => [
      entry.header,
      ...entry.children.slice(0, take(entry.children.length)),
    ]),
    ...more,
  ];
  // The blank row a finished message starts with, so the text does not move when it is written.
  const gapRow = text && !state.live.fence && gapBefore(state.done.at(-1), { kind: "message" }) ? take(1) : 0;
  // The text takes every row left; when it is taller still, one row says how much is above it.
  const textRows = firstTextRow + take(free);
  const { source, omitted } = textRows ? liveSource(text) : { source: "", omitted: "" };
  // The rows the written block will have: the same layout, its first row marked when it starts an item.
  const lead = state.done.at(-1)?.kind !== "message" && !omitted;
  const shown = liveHold(source);
  const rendered = textRows && shown ? answerRows(shown, { columns, unicode, lead }) : [];
  // What was left out before the rendered tail counts too, as plain wrapped rows.
  // Its last line break only ends its last row (a paragraph break leaves one blank row).
  const left = omitted ? tailRows(omitted.replace(/\n$/, ""), columns, Number.MAX_SAFE_INTEGER).length : 0;
  const hidden =
    textRows > 1 && rendered.length + left > textRows ? rendered.length + left - textRows + 1 : 0;
  const streamed = [
    ...(hidden
      ? [{ key: "text:above", role: "detail", text: message("app.linesAbove", { count: hidden }) }]
      : []),
    ...rendered.slice(Math.max(0, rendered.length - textRows + (hidden ? 1 : 0))).map((row, index) => ({
      key: `text:${index}`,
      text: row,
    })),
  ];
  const gap: LiveLine[] = gapRow && streamed.length ? [{ key: "text:gap", text: "" }] : [];
  // What goes to the scrollback next comes first, so it is written where it already stood.
  return [...thought, ...thinkingHeader, ...gap, ...streamed, ...shownPlan, ...listed];
}

/** The live region, in the rows the window has left after `reserved` rows below it (an input line). */
function LiveRegion({ state, reserved }: { state: TranscriptState; reserved: number }) {
  const { columns, rows } = useWindowSize();
  const theme = useTheme();
  const { unicode } = theme;
  const roles = useRoles();
  const [now, setNow] = useState(Date.now);
  const lines = liveLines(state, columns, Math.max(0, rows - reserved), now, unicode);
  // The spinner moves, and the times go up, only while a spinning or timed row is on screen.
  const moving = lines.some((line) => line.glyph?.spins || line.key === "thinking");
  useEffect(() => {
    if (!moving) return;
    const timer = setInterval(() => setNow(Date.now()), SPINNER_MS); // not a limit: the spinner's pace
    return () => clearInterval(timer);
  }, [moving]);
  // One <Text> per row, truncated: a row never wraps again, even before a resize reaches this render.
  return (
    <Box flexDirection="column">
      {lines.map((line) => (
        <Text key={line.key} wrap="truncate">
          {" ".repeat(line.indent ?? (line.glyph ? 2 : 0))}
          {line.glyph ? (
            <>
              <Text {...(line.glyph.accent ? roles.accent : line.glyph.detail ? roles.detail : {})}>
                {line.glyph.text}
              </Text>{" "}
            </>
          ) : null}
          {line.mark ? (
            <Text {...(line.markDone ? roles.success : roles.error)}>{`${line.mark} `}</Text>
          ) : null}
          {line.head ? (
            <Text
              {...(line.headAgent
                ? agentStyle(theme, line.headAgent)
                : line.headRole
                  ? roles[line.headRole]
                  : {})}
            >
              {line.head}
            </Text>
          ) : null}
          <Text {...(line.role ? roles[line.role] : {})} italic={line.italic === true}>
            {line.text || (line.glyph || line.head || line.tail ? "" : " ")}
          </Text>
          {line.tail?.map((part, index) => (
            // biome-ignore lint/suspicious/noArrayIndexKey: a part's place in the row is its identity
            <Text key={index} {...(part.role ? roles[part.role] : {})}>
              {part.text}
            </Text>
          ))}
        </Text>
      ))}
    </Box>
  );
}

export function Transcript({ state, reserved = 0 }: { state: TranscriptState; reserved?: number }) {
  // One reading of the width for every finished row written now.
  const { columns } = useWindowSize();
  return (
    <>
      <Static items={state.done}>
        {(block) => <BlockView key={block.id} block={block} columns={columns} />}
      </Static>
      <LiveRegion state={state} reserved={reserved} />
    </>
  );
}

/**
 * A group's calls, one row each: what the call was, then its preview's first row (else its summary). What
 * they were lines up across the calls; the previews' cells line up among calls to the same tool, a column
 * set right when it is in every one of their previews that has it.
 */
function groupRows(calls: readonly GroupedCall[], what: (call: GroupedCall) => string): string[] {
  const shown = calls.map((call) => (call.failed ? undefined : call.preview));
  const texts: string[] = calls.map((call, index) =>
    call.failed || shown[index] ? "" : oneLine(call.summary ?? ""),
  );
  for (const name of new Set(calls.map((call) => call.name))) {
    const members = calls.flatMap((call, index) => (call.name === name && shown[index] ? [index] : []));
    const previews = members.map((index) => shown[index] as Preview);
    const count = Math.max(0, ...previews.map((preview) => preview.rows[0]?.length ?? 0));
    const right = new Set(
      Array.from({ length: count }, (_, column) => column).filter((column) =>
        previews.every(
          (preview) => (preview.rows[0]?.length ?? 0) <= column || (preview.right ?? []).includes(column),
        ),
      ),
    );
    const aligned = alignRows(
      previews.map((preview) => preview.rows[0] ?? []),
      right,
    );
    members.forEach((index, at) => {
      texts[index] = aligned[at] ?? "";
    });
  }
  // The previews are set already: only what each call was is padded, to the widest.
  const named = calls.map((call) => printable(what(call)).replace(/\s+/g, " ").trim());
  const width = Math.max(0, ...named.map((one) => stringWidth(one)));
  return named.map((one, index) =>
    texts[index] ? `${one}${" ".repeat(width - stringWidth(one))}  ${texts[index]}` : one,
  );
}

/** An agent's name as its row shows it: bold, in the agent's own colour (the figure's hue). */
function agentStyle(theme: Theme, agent: string): { color?: string; bold: true } {
  const color = agentColour(theme, agent);
  return color ? { color, bold: true } : { bold: true };
}

/** How many tools an agent used and how long it took (or has taken): "9 tools | 1m 12s". */
function agentMeta(calls: number | undefined, time: string): string {
  return [calls ? message("app.toolCount", { count: calls }) : "", time].filter(Boolean).join(SEPARATOR);
}

/**
 * One agent's row, live or finished, in `width` cells after its glyph or mark: its name, then the title the main
 * agent gave it (dim), and its tools and time at the right edge; the title gives way first.
 */
function agentLine(
  member: { label: string; title?: string },
  meta: string,
  width: number,
): { name: string; rest: string } {
  const laid = besideMeta(
    [
      { text: printable(member.label), shrink: 0 },
      { text: agentWords(member), shrink: 2, gap: "  " },
    ],
    meta,
    width,
  );
  const [name = printable(member.label), words = ""] = laid.fields;
  return {
    name,
    rest: `${words ? `  ${words}` : ""}${laid.meta ? `${" ".repeat(laid.gap)}${laid.meta}` : ""}`,
  };
}

/** What an agent's row says beside its name: the title the main agent gave it. */
function agentWords(member: { title?: string }): string {
  return oneLine(member.title ?? "");
}

/**
 * The live rows of the sub-agents running: one alone is a row of its own, its newest call under it; several
 * are one group under a header ("Running 2 agents"), each a row with its newest call under it while it runs.
 */
function agentEntries(
  state: TranscriptState,
  moving: NonNullable<LiveLine["glyph"]>,
  columns: number,
  now: number,
  unicode: boolean,
): { header: LiveLine; children: LiveLine[] }[] {
  const { agents } = state.live;
  if (!agents.length) return [];
  const child = unicode ? "⎿" : "\\";
  const doing = (agent: (typeof agents)[number]) => {
    // A step asked for again says so in place of its call until the agent goes on.
    const { retrying } = agent;
    if (retrying) {
      const which =
        retrying.attempt !== undefined && retrying.of !== undefined
          ? ` (${message("app.retryOf", { attempt: retrying.attempt, of: retrying.of })})`
          : "";
      return `${message("app.phaseReconnecting")}${which}`;
    }
    const running = state.live.tools.filter((tool) => tool.nested && tool.run === agent.run).at(-1);
    return running
      ? oneLine(named(running.name, running.label ?? ""))
      : agent.activity
        ? oneLine(agent.activity)
        : "";
  };
  if (agents.length === 1) {
    // One alone (never finished while live: the group closes when its last member ends): its row, then the
    // call under way under it.
    const [agent] = agents as [(typeof agents)[number]];
    const { name, rest } = agentLine(
      agent,
      agentMeta(state.live.calls[agent.run], runningFor(agent.startedAt, now)),
      Math.max(1, columns - 2),
    );
    const call = doing(agent);
    return [
      {
        header: {
          key: JSON.stringify(["agent", agent.run]),
          indent: 0,
          glyph: moving,
          head: name,
          headAgent: agent.agent,
          role: "detail" as const,
          text: rest,
        },
        children: call
          ? [
              {
                key: JSON.stringify(["agent", agent.run, "doing"]),
                indent: 2,
                role: "detail",
                text: `${child} ${call}`,
              },
            ]
          : [],
      },
    ];
  }
  // Several: a heading, then one row each as a table (name, title, the call under way, tools and time), each
  // member with its own state: the spinner while it works, then ✓, or ✗ when it failed or was stopped.
  const table = agentTable(
    agents.map((agent) => {
      const finished = agent.finished;
      return {
        name: printable(agent.label),
        title: agentWords(agent),
        call: finished ? "" : doing(agent),
        calls: finished ? finished.calls : state.live.calls[agent.run],
        time: finished
          ? finished.elapsedMs !== undefined
            ? shortDuration(finished.elapsedMs)
            : ""
          : runningFor(agent.startedAt, now),
      };
    }),
    Math.max(1, columns - 4),
  );
  return [
    {
      header: {
        key: "agents",
        indent: 2,
        head: message("app.agentsRunning", { count: agents.length }),
        headRole: "title" as const,
        text: "",
      },
      children: [],
    },
    ...agents.map((agent, index) => {
      const finished = agent.finished;
      const failed = finished !== undefined && finished.status !== "done" && finished.status !== "capped";
      const { head, title, call, meta } = table[index] ?? { head: "", title: "", call: "", meta: "" };
      const line: LiveLine = {
        key: JSON.stringify(["agent", agent.run]),
        indent: 2,
        ...(finished
          ? { mark: mark(failed, unicode), ...(failed ? {} : { markDone: true }) }
          : { glyph: moving }),
        head,
        headAgent: agent.agent,
        // The title and the metrics dim; the call under way in the default text, so it stands out from them.
        role: "detail" as const,
        text: title,
        tail: [{ text: call }, { text: meta, role: "detail" as const }],
      };
      return { header: line, children: [] };
    }),
  ];
}

/** An agent group's left columns: name, title, the call under way. */
const AGENT_COLUMNS: readonly Column[] = [
  { cap: 22, min: 6, shrink: 1 },
  { cap: 34, min: 10, shrink: 2 },
  { cap: 30, min: 8, shrink: 3 },
];

/**
 * An agent group's rows in `width` cells: the name (the row's head), then its title and the call under way as
 * left-aligned columns, and its tools and time at the right edge, where every row's time is; tool counts and
 * times each right-aligned among the members. The metrics stay while the window allows; the columns give
 * way first (see tableWidths).
 */
function agentTable(
  members: readonly { name: string; title: string; call: string; calls?: number | undefined; time: string }[],
  width: number,
): { head: string; title: string; call: string; meta: string }[] {
  const tools = members.map((member) =>
    member.calls ? message("app.toolCount", { count: member.calls }) : "",
  );
  const toolsWidth = Math.max(0, ...tools.map((text) => stringWidth(text)));
  const timeWidth = Math.max(0, ...members.map((member) => stringWidth(member.time)));
  const metas = members.map((member, index) => {
    const count = tools[index] ?? "";
    const counted = toolsWidth
      ? `${count.padStart(toolsWidth)}${count && member.time ? SEPARATOR : " ".repeat(SEPARATOR.length)}`
      : "";
    const meta = `${counted}${member.time.padStart(timeWidth)}`;
    return meta.trim() ? meta : "";
  });
  const metaWidth = Math.max(0, ...metas.map((text) => stringWidth(text)));
  // The metrics only when the name keeps a useful width beside them.
  const keepMeta = metaWidth > 0 && width - metaWidth - TABLE_GAP.length >= 12;
  const left = keepMeta ? width - metaWidth - TABLE_GAP.length : width;
  const cells = members.map((member) => [member.name, member.title, member.call]);
  const widths = tableWidths(cells, AGENT_COLUMNS, left);
  return members.map((_, index) => {
    const [head = "", title = "", call] = tableRow(cells[index] ?? [], widths, AGENT_COLUMNS);
    // The cells after the name, each after the gap: the call's column is dropped first in a narrow window.
    const titled = `${TABLE_GAP}${title}`;
    const called = call !== undefined ? `${TABLE_GAP}${call}` : "";
    if (!keepMeta)
      return { head, title: called ? titled : titled.trimEnd(), call: called.trimEnd(), meta: "" };
    const used = stringWidth(head) + stringWidth(titled) + stringWidth(called);
    const meta = metas[index] ?? "";
    return {
      head,
      title: titled,
      call: called,
      meta: `${" ".repeat(Math.max(TABLE_GAP.length, width - used - metaWidth))}${meta.padStart(metaWidth)}`,
    };
  });
}

/** A finished group of sub-agents (or one alone): see agentEntries for the live rows it ends as. */
function AgentGroup({ block, columns }: { block: Extract<Block, { kind: "agents" }>; columns: number }) {
  const theme = useTheme();
  const roles = useRoles();
  const { unicode } = theme;
  const child = unicode ? "⎿" : "\\";
  const solo = block.members.length === 1;
  const failed = block.members.filter((member) => member.status === "failed").length;
  const stopped = block.members.every((member) => member.status === "stopped");
  // One alone: ✓ or ✗ and its row, and why under it when it did not finish.
  const soloRow = (member: AgentMember, index: number) => {
    const ended = member.status === "done" || member.status === "capped";
    const sign = mark(!ended, unicode);
    const meta = agentMeta(
      member.calls,
      member.elapsedMs !== undefined ? shortDuration(member.elapsedMs) : "",
    );
    const { name, rest } = agentLine(member, meta, Math.max(10, columns - 2));
    const why =
      member.status === "failed" || member.status === "capped"
        ? member.reason
        : member.status === "stopped"
          ? message("app.agentStopped")
          : undefined;
    return (
      <Box key={index} flexDirection="column">
        <Text wrap="truncate">
          <Text {...(ended ? roles.success : roles.error)}>{`${sign} `}</Text>
          <Text {...agentStyle(theme, member.agent)}>{name}</Text>
          {rest ? <Text {...roles.detail}>{rest}</Text> : null}
        </Text>
        {why ? (
          <Text
            wrap="truncate"
            {...(member.status === "failed"
              ? roles.error
              : member.status === "capped"
                ? roles.warning
                : roles.detail)}
          >
            {`  ${child} `}
            {oneLine(why)}
          </Text>
        ) : null}
      </Box>
    );
  };
  if (solo) return <Box flexDirection="column">{block.members.map(soloRow)}</Box>;
  // Several: a heading, then the members as the table they were while running (no call under way now),
  // each with how it ended (✓, or ✗ when it failed or was stopped) and why under it when it did not finish.
  const table = agentTable(
    block.members.map((member) => ({
      name: printable(member.label),
      title: agentWords(member),
      call: "",
      ...(member.calls ? { calls: member.calls } : {}),
      time: member.elapsedMs !== undefined ? shortDuration(member.elapsedMs) : "",
    })),
    Math.max(10, columns - 4),
  );
  return (
    <Box flexDirection="column">
      <Text wrap="truncate">
        {"  "}
        <Text {...roles.title}>
          {message(stopped ? "app.agentsStopped" : "app.agentsFinished", { count: block.members.length })}
        </Text>
        {failed && !stopped ? (
          <Text {...roles.error}>{`${SEPARATOR}${message("app.failedCount", { count: failed })}`}</Text>
        ) : null}
      </Text>
      {block.members.map((member, index) => {
        const ended = member.status === "done" || member.status === "capped";
        const cells = table[index];
        const head = cells?.head ?? "";
        // No call under way once finished: the title and the metrics, dim.
        const text = cells ? `${cells.title}${cells.call}${cells.meta}` : "";
        const why = member.status === "failed" || member.status === "capped" ? member.reason : undefined;
        return (
          // biome-ignore lint/suspicious/noArrayIndexKey: the members of one finished block never change
          <Box key={index} flexDirection="column">
            <Text wrap="truncate">
              {"  "}
              <Text {...(ended ? roles.success : member.status === "stopped" ? roles.detail : roles.error)}>
                {`${mark(!ended, unicode)} `}
              </Text>
              <Text {...agentStyle(theme, member.agent)}>{head}</Text>
              {text ? <Text {...roles.detail}>{text}</Text> : null}
            </Text>
            {why ? (
              <Text wrap="truncate" {...(member.status === "failed" ? roles.error : roles.warning)}>
                {" ".repeat(4)}
                {oneLine(why)}
              </Text>
            ) : null}
          </Box>
        );
      })}
    </Box>
  );
}

/**
 * A command's list: each section's heading (title role) with where it comes from beside it (dim), its rows (a
 * name, then its text in a column shared by every section; wrapped under that column, or cut to one row when
 * the list says so), a dim note under them; a blank row between sections; the links last.
 */
function ListBlock({
  block,
  columns,
  unicode,
}: {
  block: Extract<Block, { kind: "list" }>;
  columns: number;
  unicode: boolean;
}) {
  const roles = useRoles();
  const { list } = block;
  const column = listColumn(list, (text) => stringWidth(printable(text)));
  return (
    <Box flexDirection="column" paddingLeft={2} width={columns}>
      {list.sections.map((section, index) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: the sections of one finished block never change
        <Box key={index} flexDirection="column" marginTop={index > 0 ? 1 : 0}>
          {section.heading ? (
            <Text wrap="truncate">
              <Text {...roles.title}>{printable(section.heading)}</Text>
              {section.aside ? <Text {...roles.detail}>{`  ${printable(section.aside)}`}</Text> : null}
            </Text>
          ) : null}
          {(section.rows ?? []).map((row, at) => {
            const name = printable(row.name);
            return (
              // biome-ignore lint/suspicious/noArrayIndexKey: the rows of one finished block never change
              <Box key={at}>
                <Box width={Math.max(column, stringWidth(name) + 2)} flexShrink={0}>
                  <Text {...(section.labels ? roles.detail : roles.name)}>{name}</Text>
                </Box>
                <Text wrap={list.oneLine ? "truncate-end" : "wrap"}>
                  <Text {...(section.labels ? {} : roles.detail)}>{printable(row.text ?? "")}</Text>
                  {row.warn ? <Text {...roles.warning}>{`  ${printable(row.warn)}`}</Text> : null}
                </Text>
              </Box>
            );
          })}
          {(section.items ?? []).flatMap((item, at) =>
            // An item wraps between words under its text, not under its bullet.
            wrapAnsi(printable(item), Math.max(1, columns - 4), { hard: true })
              .split("\n")
              .map((row, index) => (
                // biome-ignore lint/suspicious/noArrayIndexKey: the rows of one finished block never change
                <Text key={`${at}:${index}`} wrap="truncate">
                  <Text {...roles.detail}>{index ? "  " : "- "}</Text>
                  {row}
                </Text>
              )),
          )}
          {section.note ? (
            <Box marginTop={1}>
              <Text {...roles.detail}>{printable(section.note)}</Text>
            </Box>
          ) : null}
        </Box>
      ))}
      {block.links ? (
        <Box marginTop={1}>
          <Text {...roles.detail} wrap="truncate">
            {block.links.map((link) => hyperlink(printable(link.text), link.url, unicode)).join(SEPARATOR)}
          </Text>
        </Box>
      ) : null}
    </Box>
  );
}
