// Copyright 2026 Tauric Research
// SPDX-License-Identifier: Apache-2.0
/**
 * An answer's Markdown as the parts a report is set from: headings, paragraphs of styled runs, lists,
 * tables, code and quotes. Plain data, so what a report holds can be checked without drawing it; pdf.ts
 * draws it. Every piece of text is made printable here.
 */
import type { Token, Tokens } from "marked";
import { printable } from "../../contracts/index.js";
import { decodeEntities } from "../entities.js";
import { lexAnswer } from "../lex.js";

/** A stretch of text in one style; `cite` a citation such as [1] or [2, 3]; `link` where it points. */
export type Run = { text: string; bold?: true; italic?: true; code?: true; cite?: true; link?: string };

export type Part =
  | { kind: "heading"; depth: number; runs: Run[] }
  | { kind: "paragraph"; runs: Run[] }
  /** Each item its own parts (a paragraph, a nested list). */
  | { kind: "list"; ordered: boolean; start: number; items: Part[][] }
  /** Cells as plain text; `align` per column. */
  | { kind: "table"; header: string[]; rows: string[][]; align: ("left" | "center" | "right")[] }
  | { kind: "code"; text: string }
  | { kind: "quote"; parts: Part[] }
  | { kind: "rule" };

/** A citation as the answer shows it, numbered: [1], [2, 3]. */
const CITATION = /\[\d+(?:,\s*\d+)*\]/g;

/** `source`, an answer in Markdown, as report parts. */
export function reportParts(source: string): Part[] {
  return parts(lexAnswer(source));
}

function parts(tokens: readonly Token[]): Part[] {
  return tokens.flatMap((token): Part[] => {
    switch (token.type) {
      case "heading": {
        const { depth, tokens: inner } = token as Tokens.Heading;
        return [{ kind: "heading", depth, runs: runs(inner) }];
      }
      case "paragraph":
        return [{ kind: "paragraph", runs: runs((token as Tokens.Paragraph).tokens) }];
      case "text": {
        const text = token as Tokens.Text;
        return [
          { kind: "paragraph", runs: text.tokens ? runs(text.tokens) : plain(decodeEntities(text.text)) },
        ];
      }
      case "list": {
        const list = token as Tokens.List;
        return [
          {
            kind: "list",
            ordered: list.ordered,
            start: typeof list.start === "number" ? list.start : 1,
            items: list.items.map((item) => parts(item.tokens)),
          },
        ];
      }
      case "table": {
        const table = token as Tokens.Table;
        return [
          {
            kind: "table",
            header: table.header.map((cell) => cellText(cell.tokens)),
            rows: table.rows.map((row) => row.map((cell) => cellText(cell.tokens))),
            align: table.align.map((align) => align ?? "left"),
          },
        ];
      }
      case "code":
        return [{ kind: "code", text: printable((token as Tokens.Code).text) }];
      case "blockquote":
        return [{ kind: "quote", parts: parts((token as Tokens.Blockquote).tokens) }];
      case "hr":
        return [{ kind: "rule" }];
      case "space":
      case "def":
        return [];
      default:
        return "raw" in token && String(token.raw).trim()
          ? [{ kind: "paragraph", runs: plain(String(token.raw).trim()) }]
          : [];
    }
  });
}

/** Text in the body style, its citations marked. */
function plain(text: string, style: Omit<Run, "text"> = {}): Run[] {
  const out: Run[] = [];
  let at = 0;
  for (const match of printable(text).matchAll(CITATION)) {
    const index = match.index ?? 0;
    if (index > at) out.push({ ...style, text: printable(text).slice(at, index) });
    out.push({ ...style, text: match[0], cite: true });
    at = index + match[0].length;
  }
  const rest = printable(text).slice(at);
  if (rest) out.push({ ...style, text: rest });
  return out;
}

function runs(tokens: readonly Token[] | undefined, style: Omit<Run, "text"> = {}): Run[] {
  return merged(
    (tokens ?? []).flatMap((token): Run[] => {
      switch (token.type) {
        case "strong":
          return runs((token as Tokens.Strong).tokens, { ...style, bold: true });
        case "em":
          return runs((token as Tokens.Em).tokens, { ...style, italic: true });
        case "del":
          return runs((token as Tokens.Del).tokens, style);
        case "codespan":
          return [{ ...style, text: printable(decodeEntities((token as Tokens.Codespan).text)), code: true }];
        case "link": {
          const link = token as Tokens.Link;
          // Only web links are kept as links; anything else is its text.
          const href = /^https?:\/\//i.test(link.href) ? { link: printable(link.href) } : {};
          return runs(link.tokens, { ...style, ...href });
        }
        case "image": {
          const image = token as Tokens.Image;
          return plain(image.text, style);
        }
        case "br":
          return [{ ...style, text: "\n" }];
        case "html": {
          const raw = String((token as Tokens.HTML).raw);
          return /^<br\s*\/?>$/i.test(raw.trim()) ? [{ ...style, text: "\n" }] : plain(raw, style);
        }
        case "text": {
          const text = token as Tokens.Text;
          return text.tokens ? runs(text.tokens, style) : plain(decodeEntities(text.text), style);
        }
        case "escape":
          return plain((token as Tokens.Escape).text, style);
        default:
          return "raw" in token ? plain(String(token.raw), style) : [];
      }
    }),
  );
}

/** Neighbouring runs of one style as one. */
function merged(list: Run[]): Run[] {
  const out: Run[] = [];
  for (const run of list) {
    const last = out.at(-1);
    const { text: _a, ...a } = last ?? { text: "" };
    const { text: _b, ...b } = run;
    if (last && !run.cite && !last.cite && JSON.stringify(a) === JSON.stringify(b)) last.text += run.text;
    else out.push({ ...run });
  }
  return out;
}

/** A table cell as plain text: a table cell holds one line. */
function cellText(tokens: readonly Token[]): string {
  return runs(tokens)
    .map((run) => run.text)
    .join("")
    .replace(/\s+/g, " ")
    .trim();
}
