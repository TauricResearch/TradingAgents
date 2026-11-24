// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * Markdown as terminal text: the model writes Markdown, and the transcript shows it styled (bold,
 * code, lists, tables) instead of as raw asterisks. Partial Markdown, as it streams, renders too;
 * what is not closed yet shows as typed. Every piece of text is made printable before it is
 * styled, so nothing the model writes can reach the terminal as a control sequence.
 */

import { stripVTControlCharacters } from "node:util";
import chalk, { type ChalkInstance } from "chalk";
import type { Token, Tokens } from "marked";
import stringWidth from "string-width";
import wrapAnsi from "wrap-ansi";
import { printable } from "../contracts/index.js";
import { decodeEntities } from "./entities.js";
import { lexAnswer } from "./lex.js";
import { paint, TEXT_ROLES } from "./theme.js";

/**
 * `width`: the cells each line may take (prose wraps to the narrower of it and 100, tables and code use all
 * of it; unlimited when not given). `unicode`: box-drawing borders, else ASCII.
 */
type MarkdownOptions = { width?: number; unicode?: boolean };

type Context = { style: ChalkInstance; width: number; unicode: boolean };

/** The widest a paragraph is set: lines longer than this read poorly. */
const MEASURE = 100;

export function renderMarkdown(
  source: string,
  style: ChalkInstance = chalk,
  { width = Number.POSITIVE_INFINITY, unicode = true }: MarkdownOptions = {},
): string {
  const text = blocks(lexAnswer(source), { style, width: Math.max(1, width), unicode }, "\n\n").trimEnd();
  if (!Number.isFinite(width)) return text;
  // Deep nesting in a tiny window can still leave a line too wide: it is cut into rows that fit.
  return text
    .split("\n")
    .flatMap((line) =>
      stringWidth(line) > width
        ? wrapAnsi(line, Math.max(1, width), { hard: true, trim: false }).split("\n")
        : [line],
    )
    .join("\n");
}

/**
 * `text` wrapped to `width` cells (a word longer than the width is cut); unlimited width leaves it.
 * `keepSpaces`: code, whose leading and trailing spaces are its own.
 */
function wrap(text: string, width: number, keepSpaces = false): string {
  return Number.isFinite(width)
    ? wrapAnsi(text, Math.max(1, width), { hard: true, ...(keepSpaces ? { trim: false } : {}) })
    : text;
}

/** The last answer laid out: a live answer is laid out again on each frame, often unchanged. */
let lastLayout: { key: string; rows: string[] } | undefined;

/** Narrower than this and the gutter would crowd the text: it is left out. */
const GUTTER_MIN = 12;

/**
 * An answer as the rows the transcript shows, the same live and written: laid out in the width left by a
 * two-cell gutter, the first row of an item (`lead`) marked with a dot.
 */
export function answerRows(
  text: string,
  {
    columns,
    unicode = true,
    lead,
    style = chalk,
  }: { columns: number; unicode?: boolean; lead: boolean; style?: ChalkInstance },
): string[] {
  const key = JSON.stringify([text, columns, unicode, lead, style.level]);
  if (lastLayout?.key === key) return lastLayout.rows;
  const gutter = columns >= GUTTER_MIN;
  const rendered = renderMarkdown(text, style, { width: gutter ? columns - 2 : columns, unicode });
  // Nothing visible (a link definition, say): no rows, and no mark on an empty one.
  const lines = rendered.trim() ? rendered.split("\n") : [];
  const rows = gutter
    ? lines.map((row, index) => `${index === 0 && lead ? (unicode ? "● " : "* ") : "  "}${row}`)
    : lines;
  lastLayout = { key, rows };
  return rows;
}

/** At most this much of a streaming answer is rendered: the live region shows only its last rows. */
const LIVE_SOURCE = 4_000;

/**
 * The part of a streaming answer worth rendering: its tail, from a paragraph break, reopening a code
 * block the cut lands in, and the text left out before it (off the live region anyway, but counted).
 */
export function liveSource(text: string): { source: string; omitted: string } {
  if (text.length <= LIVE_SOURCE) return { source: text, omitted: "" };
  // From a paragraph break, else a line break, so no line is cut in two.
  const paragraph = text.indexOf("\n\n", text.length - LIVE_SOURCE);
  const line = text.indexOf("\n", text.length - LIVE_SOURCE);
  const cut = paragraph >= 0 ? paragraph + 2 : line >= 0 ? line + 1 : text.length - LIVE_SOURCE;
  const start = tableStart(text, cut);
  const fences = (text.slice(0, start).match(/^```/gm) ?? []).length;
  return { source: `${fences % 2 ? "```\n" : ""}${text.slice(start)}`, omitted: text.slice(0, start) };
}

/** A line of a pipe table: its header or a row (from a pipe), or a delimiter row (with or without its outer pipes). */
const TABLE_LINE = /^ {0,3}(?:\||\|?\s*:?-+:?\s*(?:\|\s*:?-+:?\s*)+\|?\s*$)/;
/** Lines a backward scan for a table's header looks through at most. */
const TABLE_SCAN = 400;

/**
 * Where a cut at `cut` should start so that it does not land inside a table: at the table's header when
 * the cut falls among its rows (a table shows at most its first rows anyway), else at `cut`.
 */
function tableStart(text: string, cut: number): number {
  let start = cut;
  for (
    let scanned = 0;
    scanned < TABLE_SCAN &&
    start > 0 &&
    TABLE_LINE.test(text.slice(start, text.indexOf("\n", start) + 1 || undefined));
    scanned++
  ) {
    const previous = text.lastIndexOf("\n", start - 2) + 1;
    if (!TABLE_LINE.test(text.slice(previous, start))) break;
    start = previous;
  }
  return start;
}

/**
 * What of a streaming answer to show now: a table row still being typed, and a header line that may yet
 * become a table, are held back until they are whole, so the grid does not flash as raw pipes or jump. Only
 * the live view is held; what is written keeps every byte.
 */
export function liveHold(text: string): string {
  // Inside a code block nothing is a table.
  if (((text.match(/^ {0,3}(?:```|~~~)/gm) ?? []).length & 1) === 1) return text;
  const lines = text.split("\n");
  // A row still being typed (no line break yet).
  if (TABLE_LINE.test(lines.at(-1) ?? "")) lines.splice(-1, 1, "");
  else if (lines.at(-1) !== "") return text;
  // A last pipe line with no table above it, and nothing after it yet, may be a header still waiting for
  // its delimiter; one a blank line has ended is not.
  const last = lines.findLastIndex((row) => row !== "");
  const waiting = last === lines.length - 2;
  if (waiting && TABLE_LINE.test(lines[last] ?? "") && !TABLE_LINE.test(lines[last - 1] ?? "")) {
    lines.splice(last, lines.length - last, "");
  }
  return lines.join("\n");
}

function blocks(tokens: Token[], context: Context, separator: string): string {
  return tokens
    .map((token) => block(token, context))
    .filter((text) => text !== undefined)
    .join(separator);
}

function block(token: Token, context: Context): string | undefined {
  const { style, width } = context;
  switch (token.type) {
    case "space":
    case "def": // link reference definitions are lookups, not content
      return undefined;
    case "heading": {
      const { depth, tokens } = token as Tokens.Heading;
      const text = inline(tokens, style);
      const styled =
        depth === 1
          ? style.bold.underline(text)
          : depth === 2
            ? style.bold(text)
            : paint(style.bold, TEXT_ROLES.detail, text);
      return wrap(styled, width);
    }
    case "paragraph":
      return wrap(inline((token as Tokens.Paragraph).tokens, style), Math.min(width, MEASURE));
    case "text": {
      const text = token as Tokens.Text;
      return wrap(text.tokens ? inline(text.tokens, style) : printable(decodeEntities(text.text)), width);
    }
    case "code":
      // Code keeps its own line breaks; a line longer than the width is cut into rows.
      return printable((token as Tokens.Code).text)
        .split("\n")
        .flatMap((line) => wrap(line, width - 2, true).split("\n"))
        .map((line) => `  ${paint(style, TEXT_ROLES.code, line)}`)
        .join("\n");
    case "blockquote":
      return blocks(
        (token as Tokens.Blockquote).tokens,
        { ...context, width: Math.max(1, width - 2) },
        "\n\n",
      )
        .split("\n")
        .map((line) => `${paint(style, TEXT_ROLES.detail, "│")} ${line}`)
        .join("\n");
    case "list":
      return list(token as Tokens.List, context);
    case "table":
      return table(token as Tokens.Table, context);
    case "hr":
      return paint(
        style,
        TEXT_ROLES.detail,
        (context.unicode ? "─" : "-").repeat(Number.isFinite(width) ? Math.max(1, width) : 30),
      );
    default:
      return "raw" in token ? printable(String(token.raw)).trimEnd() : undefined;
  }
}

function list(token: Tokens.List, context: Context): string {
  const start = typeof token.start === "number" ? token.start : 1;
  // A loose list keeps a blank line between its items and between an item's paragraphs.
  const gap = token.loose ? "\n\n" : "\n";
  return token.items
    .map((item, index) => {
      const marker = token.ordered ? `${start + index}.` : "-";
      const checkbox = item.task ? `[${item.checked ? "x" : " "}] ` : "";
      const children = item.tokens.filter((child) => child.type !== "checkbox");
      const pad = " ".repeat(marker.length + 1);
      // The item's text is laid out in the width left after its marker (and its checkbox).
      const room = Math.max(1, context.width - pad.length - checkbox.length);
      const body = `${checkbox}${blocks(children, { ...context, width: room }, gap)}`;
      const [first = "", ...rest] = body.split("\n");
      return [`${marker} ${first}`, ...rest.map((line) => (line ? `${pad}${line}` : line))].join("\n");
    })
    .join(gap);
}

/** Most rows of a table shown; the rest are counted. */
const TABLE_ROWS = 200;
/** A cell this many lines tall, or a table that does not fit at all, reads better as records. */
const CELL_LINES = 4;
/** The longest word a column must keep whole: a long address or name may still be cut. */
const LONGEST_WORD = 30;

/** A cell's text as a number reads: amounts, percentages, multiples, with blanks and dashes allowed. */
const NUMERIC = /^[-+−(]?[$€£¥]?\d[\d,.]*\s?[%xX]?[A-Za-z]{0,3}\)?$/;
// Dashes a model writes for "none".
const BLANK = /^(?:|\u2014|\u2013|-|N\/A|n\/a)$/;

type Align = "left" | "center" | "right";

/**
 * A table as a grid in the width, its cells wrapped when needed (with a rule between rows when any
 * wrapped), or as `header: value` records when it cannot fit. Columns align as the source says; a column
 * it says nothing about is right-aligned when all its cells are numbers.
 */
function table(token: Tokens.Table, context: Context): string {
  const { style, width, unicode } = context;
  const cells = (row: Tokens.TableCell[]) => row.map((cell) => inline(cell.tokens, style));
  const header = cells(token.header).map((cell) => style.bold(cell));
  const shown = token.rows.slice(0, TABLE_ROWS);
  const body = shown.map(cells);
  const more = token.rows.length - shown.length;
  const tail =
    more > 0
      ? `\n${paint(style, TEXT_ROLES.detail, wrap(`… ${more} more ${more === 1 ? "row" : "rows"}`, width))}`
      : "";
  const columns = header.length;
  const align: Align[] = header.map((_, column) => {
    const given = token.align[column];
    if (given) return given;
    // The cell's text without the emphasis around it: a bold number is still a number.
    const texts = shown.map((row) => (row[column]?.text ?? "").replace(/[*_`~]/g, "").trim());
    const numeric =
      texts.some((text) => NUMERIC.test(text)) &&
      texts.every((text) => NUMERIC.test(text) || BLANK.test(text));
    return numeric ? "right" : "left";
  });
  const all = [header, ...body];
  const lines = (cell: string) => cell.split("\n");
  const natural = header.map((_, column) =>
    Math.max(1, ...all.flatMap((row) => lines(row[column] ?? "").map((line) => stringWidth(line)))),
  );
  const least = header.map((_, column) =>
    Math.min(
      natural[column] ?? 1,
      Math.max(
        3,
        Math.min(
          LONGEST_WORD,
          Math.max(
            ...all.flatMap((row) =>
              words(stripVTControlCharacters(row[column] ?? "")).map((word) => stringWidth(word)),
            ),
            0,
          ),
        ),
      ),
    ),
  );
  const budget = width - (3 * columns + 1);
  const sum = (values: number[]) => values.reduce((total, value) => total + value, 0);
  let widths: number[] | undefined;
  if (sum(natural) <= budget) widths = natural;
  else if (sum(least) <= budget) {
    // The spare width goes to the columns in proportion to how much more they would take.
    const spare = budget - sum(least);
    const wants = natural.map((value, column) => value - (least[column] ?? 0));
    const wanted = sum(wants) || 1;
    const shares = wants.map((want) => (spare * want) / wanted);
    widths = least.map((value, column) => value + Math.floor(shares[column] ?? 0));
    // The cells the rounding left over go to the columns it shorted most.
    let left = budget - sum(widths);
    const order = shares
      .map((share, column) => [share - Math.floor(share), column] as const)
      .sort((a, b) => b[0] - a[0]);
    for (const [, column] of order) {
      if (left <= 0) break;
      if ((widths[column] ?? 0) < (natural[column] ?? 0)) {
        widths[column] = (widths[column] ?? 0) + 1;
        left--;
      }
    }
  }
  const laidOut = widths
    ? all.map((row) => row.map((cell, column) => cellLines(cell, widths?.[column] ?? 1)))
    : undefined;
  if (!widths || !laidOut || laidOut.some((row) => row.some((cell) => cell.length > CELL_LINES))) {
    // A table of only its header has no records: its names, as a line.
    if (!body.length) return wrap(header.join("  "), width);
    return records(header, body, context) + tail;
  }
  const glyph = unicode
    ? { h: "─", v: "│", top: "┌┬┐", mid: "├┼┤", head: "├┼┤", bottom: "└┴┘", headH: "─" }
    : { h: "-", v: "|", top: "+++", mid: "+++", head: "+++", bottom: "+++", headH: "=" };
  const rule = (corners: string, horizontal = glyph.h) =>
    paint(
      style,
      TEXT_ROLES.detail,
      `${corners[0]}${(widths as number[]).map((value) => horizontal.repeat(value + 2)).join(corners[1])}${corners[2]}`,
    );
  const row = (cellsLines: string[][]) => {
    const height = Math.max(...cellsLines.map((cell) => cell.length));
    return Array.from({ length: height }, (_, line) =>
      cellsLines
        .map((cell, column) => pad(cell[line] ?? "", widths?.[column] ?? 1, align[column] ?? "left"))
        .reduce(
          (text, cell) => `${text} ${cell} ${paint(style, TEXT_ROLES.detail, glyph.v)}`,
          paint(style, TEXT_ROLES.detail, glyph.v),
        ),
    ).join("\n");
  };
  const [head = [], ...rest] = laidOut;
  const wrapped = rest.some((cellsLines) => cellsLines.some((cell) => cell.length > 1));
  const bodyRows = rest.map(row).join(wrapped ? `\n${rule(glyph.mid)}\n` : "\n");
  return (
    [
      rule(glyph.top),
      row(head),
      rule(glyph.head, glyph.headH),
      ...(rest.length ? [bodyRows] : []),
      rule(glyph.bottom),
    ].join("\n") + tail
  );
}

const WORDS = new Intl.Segmenter(undefined, { granularity: "word" });

/** The words of a cell, to keep whole: by spaces, and by Intl.Segmenter where there are none (CJK). */
function words(cell: string): string[] {
  return cell
    .split(/\s+/)
    .flatMap((word) =>
      /^[\x20-\x7e]*$/.test(word) ? [word] : [...WORDS.segment(word)].map((part) => part.segment),
    );
}

/** A cell's lines at `width`: its own breaks kept, each wrapped by words, a longer word cut. */
function cellLines(cell: string, width: number): string[] {
  return cell.split("\n").flatMap((line) => wrapAnsi(line, width, { hard: true }).split("\n"));
}

function pad(text: string, width: number, align: Align): string {
  const room = Math.max(0, width - stringWidth(text));
  if (align === "right") return " ".repeat(room) + text;
  if (align === "center") return " ".repeat(Math.floor(room / 2)) + text + " ".repeat(Math.ceil(room / 2));
  return text + " ".repeat(room);
}

/** Each row as `header: value` lines (a long value wrapped under itself), a dim rule between rows. */
function records(header: string[], body: string[][], context: Context): string {
  const { style, width, unicode } = context;
  const separator = paint(style, TEXT_ROLES.detail, (unicode ? "─" : "-").repeat(Math.min(40, width)));
  return body
    .map((row) =>
      header
        .map((name, column) => {
          // The whole line wraps, the label too when it is long; continuation lines sit two cells in.
          const value = (row[column] ?? "").replaceAll("\n", " ");
          const [first = "", ...more] = wrap(`${name}: ${value}`, Math.max(1, width - 2)).split("\n");
          return [first, ...more.map((line) => `  ${line}`)].join("\n");
        })
        .join("\n"),
    )
    .join(`\n${separator}\n`);
}

function inline(tokens: Token[] | undefined, style: ChalkInstance): string {
  return (tokens ?? [])
    .map((token) => {
      switch (token.type) {
        case "strong":
          return style.bold(inline((token as Tokens.Strong).tokens, style));
        case "em":
          return style.italic(inline((token as Tokens.Em).tokens, style));
        case "codespan":
          return paint(style, TEXT_ROLES.code, printable(decodeEntities((token as Tokens.Codespan).text)));
        case "del":
          return style.strikethrough(inline((token as Tokens.Del).tokens, style));
        case "link": {
          const link = token as Tokens.Link;
          const text = inline(link.tokens, style);
          const href = printable(link.href);
          return href && href !== link.text
            ? `${text} ${paint(style, TEXT_ROLES.detail, `(${href})`)}`
            : text;
        }
        case "image": {
          const image = token as Tokens.Image;
          return image.tokens ? inline(image.tokens, style) : printable(image.text);
        }
        case "br":
          return "\n";
        case "html": {
          // A line break written as HTML (tables cannot hold a real one); other HTML shows as written.
          const raw = String((token as Tokens.HTML).raw);
          return /^<br\s*\/?>$/i.test(raw.trim()) ? "\n" : printable(raw);
        }
        case "text": {
          const text = token as Tokens.Text;
          return text.tokens ? inline(text.tokens, style) : printable(decodeEntities(text.text));
        }
        case "escape":
          return printable((token as Tokens.Escape).text);
        default:
          return "raw" in token ? printable(String(token.raw)) : "";
      }
    })
    .join("");
}
